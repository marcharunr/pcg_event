import requests
import time
import json
from typing import List, Dict, Optional
import random
from bs4 import BeautifulSoup
import sqlite3
import logging
from logging.handlers import TimedRotatingFileHandler
import traceback
from playwright.sync_api import sync_playwright, Page, Playwright, Browser

# ==============================================================================
# --- ユーザー設定項目 ---
# ==============================================================================
try:
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    SLACK_WEBHOOK_URL = config.get("SLACK_WEBHOOK_URL", "")
    TARGET_URL = config.get("TARGET_URL", "")
    MIN_INTERVAL_SECONDS = config.get("MIN_INTERVAL_SECONDS", 30)
    MAX_INTERVAL_SECONDS = config.get("MAX_INTERVAL_SECONDS", 60)
    HEALTHCHECKS_URL = config.get("HEALTHCHECKS_URL", "")
    SLACK_MENTION = config.get("SLACK_MENTION", "")
    DEBUG_MODE = config.get("DEBUG_MODE", False)
    INJECT_PAGE_ERROR = config.get("INJECT_PAGE_ERROR", False)
    INJECT_PARSE_ERROR = config.get("INJECT_PARSE_ERROR", False)
except FileNotFoundError:
    print("[CRITICAL] 設定ファイル 'config.json' が見つかりません。プログラムを終了します。")
    # loggingが設定される前なのでprintで出力
    exit(1)
except json.JSONDecodeError:
    print("[CRITICAL] 設定ファイル 'config.json' の形式が正しくありません。プログラムを終了します。")
    exit(1)

# --- デバッグ用設定 (コード内で直接管理) ---
DEBUG_HTML_FILE_FOUND = "test_data/rendered_found.html"
DEBUG_HTML_FILE_NOT_FOUND = "test_data/rendered_not_found.html"

# 6. 通知済みイベントを保存するデータベースファイル
# デバッグモードでは別のファイルを使用し、本番データに影響を与えないようにする
DB_FILE = "debug_notified_events.db" if DEBUG_MODE else "notified_events.db"
# ==============================================================================
# --- 内部設定 (通常は変更不要) ---
# ==============================================================================

# ==============================================================================
# --- 通知関数 ---
# ==============================================================================

def send_slack_notification(new_events: List[Dict[str, str]], is_alert: bool = False, alert_message: str = ""):
    """Slackに通知を送信する"""
    if not SLACK_WEBHOOK_URL:
        logging.info("SlackのWebhook URLが設定されていないため、通知をスキップします。")
        return

    try:
        # Slack Block Kit を使ってメッセージを構築
        if is_alert:
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚨 監視スクリプトでエラーが発生しました 🚨",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```{alert_message}```"
                    }
                }
            ]
            fallback_text = "監視スクリプトでエラーが発生しました。"
        else:
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "⚡ ポケカイベントに空きが出ました！ ⚡",
                        "emoji": True
                    }
                }
            ]

            for event in new_events:
                blocks.extend([
                    {"type": "divider"},
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*<{event['link']}|{event['name']}>*\n"
                                    f":office: {event['shop']}\n"
                                    f":round_pushpin: {event['address']}\n"
                                    f":calendar: {event['date']}"
                        }
                    }
                ])
            
            blocks.extend([
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"<{TARGET_URL}|一覧ページで確認>"
                        }
                    ]
                }
            ])
            fallback_text = f"{len(new_events)}件の新規イベントを発見しました。"
        
        # メンションが設定されていれば、メッセージの先頭に追加
        if SLACK_MENTION:
            # Block Kit用のメンション文字列を生成
            if SLACK_MENTION in ["@channel", "@here", "@everyone"]:
                mention_text = f"<!{SLACK_MENTION[1:]}>"
            elif SLACK_MENTION.startswith('@U') or SLACK_MENTION.startswith('@W'): # User or User Group
                mention_text = f"<{SLACK_MENTION}>"
            else:
                # 不明な形式はそのままテキストとして表示
                mention_text = SLACK_MENTION

            mention_block = {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": mention_text
                }
            }
            # ヘッダーの直後にメンションブロックを挿入
            blocks.insert(1, mention_block)
            # フォールバックテキストにもメンションを追加
            fallback_text = f"{mention_text} {fallback_text}"

        payload = {"text": fallback_text, "blocks": blocks}

        response = requests.post(
            SLACK_WEBHOOK_URL, 
            data=json.dumps(payload), 
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()
        logging.info("Slackに通知を送信しました。")
    except requests.exceptions.RequestException as e:
        logging.error(f"Slack通知の送信に失敗しました: {e}")

def send_heartbeat():
    """Healthchecks.ioなどの死活監視サービスにハートビートを送信する"""
    if not HEALTHCHECKS_URL:
        return  # URLが設定されていなければ何もしない

    try:
        requests.get(HEALTHCHECKS_URL, timeout=10)
        logging.info("死活監視サービスにハートビートを送信しました。")
    except requests.exceptions.RequestException as e:
        # ハートビートの失敗はメインの処理を止めないように、警告ログのみ出力
        logging.warning(f"死活監視サービスへのハートビート送信に失敗しました: {e}")


# ==============================================================================
# --- コアロジック ---
# ==============================================================================

def get_page_content(page: Optional[Page]) -> str:
    """Webページの内容を取得またはデバッグ用のファイルを読み込む"""
    try:
        # デバッグ用のエラー注入
        if DEBUG_MODE and INJECT_PAGE_ERROR:
            logging.debug("INJECT_PAGE_ERRORが有効なため、意図的にページ取得エラーを発生させます。")
            raise Exception("【テスト用】意図的に発生させたページ取得エラー")

    except Exception as e:
        # この関数内で発生したエラー（注入されたものを含む）をここで処理する
        error_info = f"ページの取得処理でエラーが発生しました。\n\n詳細:\n{traceback.format_exc()}"
        logging.error(error_info, exc_info=True)
        send_slack_notification([], is_alert=True, alert_message=error_info)
        return ""
    if DEBUG_MODE:
        logging.debug("デバッグモードで実行中。ローカルのレンダリング済みHTMLを読み込みます。")
        try:
            # 状態変化をシミュレート
            if int(time.time()) % 20 < 10:
                logging.debug(f"ファイル '{DEBUG_HTML_FILE_NOT_FOUND}' を使用します。")
                filepath = DEBUG_HTML_FILE_NOT_FOUND
            else:
                logging.debug(f"ファイル '{DEBUG_HTML_FILE_FOUND}' を使用します。")
                filepath = DEBUG_HTML_FILE_FOUND
            
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError as e:
            logging.error(f"デバッグ用のHTMLファイルが見つかりません: {e}")
            logging.info("[ヒント] `capture_html.py` を実行してモックファイルを作成してください。")
            return ""
    else:
        try:
            if not page:
                raise ValueError("通常モードではPlaywrightのPageオブジェクトが必要です。")
            page.goto(TARGET_URL, wait_until="networkidle", timeout=20000)

            # Cookie同意バナーが表示された場合に対応
            try:
                # タイムアウトを短めに設定し、バナーがなければすぐに次に進む
                page.locator('button:has-text("同意する")').click(timeout=3000)
                logging.info("Cookieに同意しました。")
            except Exception:
                # バナーがない場合はタイムアウトしてここに来るが、問題ないので処理を続ける
                pass

            # イベントリストか、「イベントなし」メッセージのどちらかが表示されるまで待つ
            page.wait_for_selector("div.noResult, a.eventListItem", timeout=15000)
            return page.content()
        except Exception as e:
            error_info = f"ページの取得処理でエラーが発生しました。\n\n詳細:\n{e}"
            logging.error(error_info, exc_info=True)
            send_slack_notification([], is_alert=True, alert_message=error_info)
            return ""

def extract_event_details(html_content: str) -> List[Dict[str, str]]:
    """HTMLの内容を解析し、イベント情報のリストを抽出する"""
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "lxml")
    
    # 「イベントなし」コンテナがあれば空のリストを返す
    if soup.select_one("div.noResult"):
        return []

    event_list = []
    # 正しいイベントカードのセレクタに変更
    event_cards = soup.select("a.eventListItem")

    for card in event_cards:
        # 新しいHTML構造に合わせてセレクタを全面的に更新
        name_tag = card.select_one("div.title")
        
        day_tag = card.select_one("span.day")
        week_tag = card.select_one("span.week")
        time_tag = card.select_one("span.time")
        shop_tag = card.select_one("div.shop a")
        address_tag = card.select_one("div.address span.building")
        
        date_str = "N/A"
        if day_tag and week_tag and time_tag:
            date_str = f"{day_tag.get_text(strip=True)} {week_tag.get_text(strip=True)} {time_tag.get_text(strip=True)}"

        name = name_tag.get_text(strip=True) if name_tag else "N/A"
        shop = shop_tag.get_text(strip=True) if shop_tag else "N/A"
        address = address_tag.get_text(strip=True) if address_tag else "N/A"
        date = date_str
        # リンクは a タグ自身から取得
        link = card['href'] if 'href' in card.attrs else ""
        
        # 相対URLを絶対URLに変換
        if link.startswith("/"):
            link = "https://players.pokemon-card.com" + link

        event_list.append({"name": name, "date": date, "link": link, "shop": shop, "address": address})

    return event_list

# ==============================================================================
# --- メイン処理 ---
# ==============================================================================

def setup_database():
    """データベースとテーブルを初期化する"""
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notified_events (
            link TEXT PRIMARY KEY,
            notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    con.commit()
    con.close()

def load_notified_events_from_db() -> set:
    """通知済みのイベントURLをDBから読み込む"""
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT link FROM notified_events")
    links = {row[0] for row in cur.fetchall()}
    con.close()
    logging.info(f"DBから{len(links)}件の通知済みイベントを読み込みました。")
    return links

def save_event_to_db(link: str):
    """通知済みのイベントをDBに保存する"""
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO notified_events (link) VALUES (?)", (link,))
    con.commit()
    con.close()

def clear_notified_events_in_db():
    """通知済みのイベントをDBからすべて削除する"""
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("DELETE FROM notified_events")
    con.commit()
    con.close()
    logging.info("通知済みイベントDBをクリアしました。")

def run_loop(page: Optional[Page]):
    """監視処理のメインループ"""
    notified_event_links = load_notified_events_from_db()
    while True:
        try:
            logging.info("ページをチェックします...")

            html = get_page_content(page)
            if not html:
                # get_page_content内でエラーが発生した場合、次のサイクルまで待つ
                logging.warning("HTMLの取得に失敗しました。次のサイクルでリトライします。")

            # デバッグ用のエラー注入
            if DEBUG_MODE and INJECT_PARSE_ERROR:
                logging.debug("INJECT_PARSE_ERRORが有効なため、意図的に解析エラーを発生させます。")
                raise Exception("【テスト用】意図的に発生させた解析エラー")

            found_events = extract_event_details(html)
            if html: # HTMLの取得が成功した場合のみ、解析と通知処理を行う
                logging.info(f"{len(found_events)}件のイベントをページ上で確認しました。")

                new_events = [event for event in found_events if event["link"] not in notified_event_links]

                if new_events:
                    logging.info("=" * 60)
                    logging.info(f"！！！新規イベントを {len(new_events)} 件発見しました！！！")
                    logging.info("=" * 60)
                    
                    for event in new_events:
                        logging.info(f"- {event['name']} ({event['date']})")
                    # Slack通知を先に試みる
                    send_slack_notification(new_events, is_alert=False)

                    # 通知が成功したら、DBとメモリ上のセットを更新
                    for event in new_events:
                        notified_event_links.add(event["link"])
                        save_event_to_db(event["link"])
                    logging.info(f"{len(new_events)}件の新規イベントを通知済みとして保存しました。")
                
                elif found_events:
                    logging.info("新規イベントはありません。引き続き募集中です。")
                else:
                    logging.info("現在、受付中のイベントはありません。")
                    if notified_event_links:
                        notified_event_links.clear()
                        clear_notified_events_in_db()

            # 正常に1サイクルが完了したことを通知
            send_heartbeat()

        except Exception as e:
            # logging.exceptionは、exceptブロック内で使うと自動でトレースバック情報をログに含めてくれる
            error_info = f"メインループ（解析処理など）でエラーが発生しました。\n\n詳細:\n{e}"
            logging.critical(error_info, exc_info=True)
            send_slack_notification([], is_alert=True, alert_message=error_info)


        # ランダムな待機時間（ジッター）を生成
        wait_time = random.uniform(MIN_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS)
        logging.info(f"次回のチェックまで {wait_time:.2f} 秒待機します。")
        time.sleep(wait_time)

def setup_logging():
    """ロギングを設定する"""
    log_format_str = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    formatter = logging.Formatter(log_format_str)
    
    # 時間ベースのローテーション設定: 毎日深夜0時にローテーションし、過去7日分を保持
    # when='midnight': 毎日深夜0時
    # interval=1: 1日ごと
    # backupCount=7: 7世代分のバックアップを保持
    file_handler = TimedRotatingFileHandler("event_monitor.log", when='midnight', interval=1, backupCount=7, encoding='utf-8')
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

def main():
    """メインの監視処理ループ"""
    setup_logging()
    logging.info("イベント監視スクリプトを開始します。")
    logging.info(f"監視対象URL: {TARGET_URL}")
    logging.info(f"チェック間隔: {MIN_INTERVAL_SECONDS}秒～{MAX_INTERVAL_SECONDS}秒のランダム")
    
    run_mode = "デバッグモード" if DEBUG_MODE else "本番モード"
    logging.info(f"実行モード: {run_mode}")
    logging.info(f"使用データベース: {DB_FILE}")

    # データベースのセットアップを最初に行う
    setup_database()

    # デバッグモードの場合、毎回クリーンな状態でテストを開始するためにDBをクリアする
    if DEBUG_MODE:
        logging.info("デバッグモードのため、通知履歴DBをクリアします。")
        clear_notified_events_in_db()

    if DEBUG_MODE:
        run_loop(None)
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True) # Trueでバックグラウンド実行
            page = browser.new_page()
            run_loop(page)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # loggingが設定される前のエラーは捕捉できないが、main内のエラーは捕捉可能
        error_message = f"スクリプトが起動シーケンス中に致命的なエラーで停止しました。\n\n詳細:\n{e}"
        # loggingが有効な場合はログに出力
        if logging.getLogger().hasHandlers():
            logging.critical(error_message, exc_info=True)
        else:
            print(error_message)
        # 致命的エラーもアラートとして通知
        send_slack_notification([], is_alert=True, alert_message=error_message)
    except KeyboardInterrupt:
        logging.info("\nスクリプトを終了します。")