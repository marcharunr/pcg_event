#!/bin/bash
#
# このスクリプトは、デバッグ用のモックHTMLファイルを自動で生成します。
#

# スクリプトのいずれかのコマンドが失敗した場合、即座に終了する
set -e

echo "[1/2] イベントが見つからない場合のモックファイルを作成します..."
python capture_html.py "https://players.pokemon-card.com/event/search?prefecture=8&prefecture=9&prefecture=10&prefecture=11&prefecture=12&prefecture=13&prefecture=14&event_type=3:2&league_type=2&offset=0&accepting=true&order=1" "test_data/rendered_not_found.html"

echo ""
echo "[2/2] イベントが見つかる場合のモックファイルを作成します..."
python capture_html.py "https://players.pokemon-card.com/event/search?event_type=3:2&league_type=2" "test_data/rendered_found.html"

echo ""
echo "✅ モックファイルの作成が完了しました。 (test_data/ ディレクトリ内)"