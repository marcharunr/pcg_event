# ポケモンカードゲーム イベント監視スクリプト (Pokémon Trading Card Game Event Monitor)

指定されたポケモンカードゲーム プレイヤーズクラブのイベント検索ページを定期的に監視し、新たなイベント（キャンセルによる空きを含む）が追加された際にSlackへ通知を送信するPythonスクリプトです。

## ✨ 主な機能

- **動的ページ対応:** JavaScriptで描画されるWebサイトに対応するため、Playwrightを使用してブラウザを自動操作します。
- **リッチなSlack通知:** SlackのBlock Kitを利用し、イベント名、店舗、場所、日時、URLなどを見やすく整形して通知します。
- **堅牢な永続化:** 通知済みのイベントをSQLiteデータベースに保存し、スクリプトの再起動後も重複した通知を防ぎます。
- **安全な設定管理:** `config.json`ファイルで設定を管理し、SlackのWebhook URLなどの秘密情報をコードから分離します。
- **高度なエラーハンドリング:** ページ取得の失敗や解析エラーを検知し、詳細なエラー内容をSlackへアラートとして通知します。
- **サーバーへの配慮:** アクセス間隔に調整し、サーバー負荷を軽減します。またアクセス間隔にランダムな「ゆらぎ（ジッター）」を持たせます。
- **詳細なロギング:** `logging`モジュールを使用し、日次でローテーションされるログファイルに全活動を記録します。
- **高機能なデバッグモード:** 本番とは分離された環境で、正常系・異常系の両方の動作を安全かつ効率的にテストできます。

## ⚙️ 動作要件

- Python 3.9 以上

## 🚀 セットアップ手順

1.  **リポジトリをクローン**
    ```bash
    git clone <repository_url>
    cd pcg_event
    ```

2.  **Python仮想環境の作成と有効化**
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    # Windowsの場合は .\.venv\Scripts\activate
    ```

3.  **依存パッケージのインストール**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Playwrightのブラウザエンジンをインストール**
    ```bash
    playwright install
    ```

5.  **設定ファイルの作成**
    `config.json.example`をコピーして`config.json`を作成します。
    ```bash
    cp config.json.example config.json
    ```
    その後、`config.json`を開き、ご自身の`SLACK_WEBHOOK_URL`を正しい値に書き換えてください。

## 🏃‍ 実行方法

### デバッグモードでの実行

スクリプトの動作や通知のテストを行うには、`config.json`の`"DEBUG_MODE"`を`true`に設定します。

まず、テスト用のモックHTMLファイルを作成します。
```bash
sh make_mock.sh
```

その後、スクリプトを実行します。
```bash
python event_checker.py
```
これにより、実際のWebサイトにはアクセスせず、ローカルのHTMLファイルを使って安全にテストが実行されます。

### 本番モードでの実行

実際に監視を開始するには、`config.json`の`"DEBUG_MODE"`を`false`に設定して、スクリプトを実行します。

```bash
python event_checker.py
```

スクリプトをバックグラウンドで永続的に実行したい場合は、`nohup`や`systemd`、`supervisor`、`launchd`などのツールを使用することを推奨します。

#### 例1: nohupによるバックグラウンド実行

```bash
nohup python event_checker_v2.py > /dev/null 2>&1 &
```

#### 例2:macOSでの自動起動・再起動 (launchd)

macOSでスクリプトを永続的に実行するには、`launchd`を利用するのが最も堅牢です。

1.  `deployment/com.user.pcg-event-monitor.plist.example` を `deployment/com.user.pcg-event-monitor.plist` としてコピーします。
2.  コピーしたファイルを開き、`__PYTHON_EXECUTABLE_PATH__`, `__SCRIPT_PATH__`, `__WORKING_DIRECTORY__` の3つのプレースホルダーを、あなたの環境の絶対パスに書き換えます。
3.  ターミナルで以下のコマンドを実行し、`deployment`ディレクトリに移動してから、`launchd`にサービスを登録・起動します。
    ```bash
    cd deployment/
    launchctl load com.user.pcg-event-monitor.plist
    ```
4.  サービスを停止・登録解除する場合は、以下のコマンドを実行します。
    ```bash
    launchctl unload com.user.pcg-event-monitor.plist
    ```

## 🔧 設定項目 (`config.json`)

- `SLACK_WEBHOOK_URL`: (必須) 通知を送信するSlackのIncoming Webhook URL。
- `TARGET_URL`: (必須) 監視対象のイベント検索ページのURL。
- `MIN_INTERVAL_SECONDS`: 最小チェック間隔（秒）。
- `MAX_INTERVAL_SECONDS`: 最大チェック間隔（秒）。この範囲でランダムに待機します。
- `DEBUG_MODE`: `true`にするとデバッグモードで実行します。
- `INJECT_PAGE_ERROR`: (デバッグ用) `true`にすると、意図的にページ取得エラーを発生させ、エラー通知をテストします。
- `INJECT_PARSE_ERROR`: (デバッグ用) `true`にすると、意図的に解析エラーを発生させ、エラー通知をテストします。

## 🛠️ 補助スクリプト

### `capture_html.py`

指定したURLのレンダリング済みHTMLをファイルに保存します。デバッグ用のモックファイルを作成・更新する際に使用します。

**使い方:**
```bash
python capture_html.py <URL> <出力ファイル名.html>
```

## 📜 ライセンス

このプロジェクトは MIT License のもとで公開されています。

## ⚠️ 免責事項

本ソフトウェアは、技術的な学習および実験を目的として作成されたものです。

本ソフトウェアの利用により、対象ウェブサイトの利用規約に違反する可能性があります。利用者は、自身の責任において本ソフトウェアを使用するものとし、本ソフトウェアの利用によって生じたいかなる損害や問題についても、作成者は一切の責任を負いません。

対象ウェブサイトの利用規約を十分に確認し、遵守してください。

## 商標について

本プロジェクト内で言及されている「ポケモン」、「ポケモンカードゲーム」、「プレイヤーズクラブ」、「Pokémon Trading Card Game」その他の関連する名称は、任天堂、クリーチャーズ、ゲームフリーク、株式会社ポケモンの登録商標または商標です。

本プロジェクトは、これらの企業とは一切関係がなく、公式に承認または後援されているものではありません。