import asyncio
from playwright.async_api import async_playwright
import sys

async def capture_rendered_html(url: str, output_file: str):
    """
    指定されたURLにアクセスし、JavaScriptがレンダリングした後のHTMLをファイルに保存する。
    """
    print(f"URLにアクセス中: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Cookie同意バナーが表示された場合に対応
            try:
                print("Cookie同意ボタンを探しています...")
                await page.locator('button:has-text("同意する")').click(timeout=5000)
                print("Cookieに同意しました。")
            except Exception:
                print("Cookie同意ボタンが見つからないか、すでに同意済みです。処理を続行します。")

            # イベントリストか「イベントなし」メッセージが表示されるまで待機
            print("コンテンツ（イベントリスト or 「イベントなし」メッセージ）の描画を待っています...")
            await page.wait_for_selector("div.noResult, a.eventListItem", timeout=20000)
            print("描画完了。HTMLをキャプチャします...")
            
            content = await page.content()
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            print(f"レンダリング後のHTMLをファイルに保存しました: {output_file}")
            
        except Exception as e:
            print(f"エラーが発生しました: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("使い方: python capture_html.py <URL> <出力ファイル名.html>")
        sys.exit(1)
    
    target_url = sys.argv[1]
    output_filename = sys.argv[2]
    asyncio.run(capture_rendered_html(target_url, output_filename))