// 公開サイトから断面図を作るための設定（空のままなら、公開サイトは閲覧専用。ローカルでは使わない）。
// 断面図API（nwp_xsection_api を Render に置いたもの）のURLを入れる。現在の設定: Render の nwp-xsection-api（2026-11-12 に有効化）
// 秘密ではない（URLが分かっても、公開サイトに載せるには合言葉が要る）。
window.NWP_XSECTION_API = "https://nwp-xsection-api.onrender.com";
