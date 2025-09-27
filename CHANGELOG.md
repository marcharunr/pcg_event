# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-09-27

### Changed
- **監視ループの堅牢性を大幅に向上**: 各チェックサイクルごとにブラウザを新しく起動し、処理後に閉じるようにメインループをリファクタリングしました。これにより、長期間の実行や一時的なネットワークエラーに対する安定性が大幅に向上しました。
- **エラーハンドリングの改善**: ページ取得時のエラーハンドリング機構を改善しました。ページ取得中に発生したエラーはメインループで一元的に捕捉され、リソースの確実なクリーンアップとアラート通知が行われるようになりました。

### Fixed
- 一時的なネットワーク切断後にスクリプトが回復不可能なエラー状態に陥り、同じエラーを繰り返し通知する問題を修正しました。

### Added
- `README.md`に、`fish`シェルで仮想環境を有効化するための手順を追記しました。

## [1.0.0] - (Initial Release Date)

### Added
- 初期リリース