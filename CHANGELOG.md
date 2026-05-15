# Changelog

## [0.2.0] - 2026-05-15

### Added

- OpenBB Workspace App bundle with Portfolio, Market Data, and Options tabs
- `widget_config` metadata for account_summary, positions, and margin_summary endpoints
- `get_apps_json_path()` helper for locating the bundled apps.json
- Workspace App documentation in README
- Integration tests for workspace bundle

### Changed

- Package now includes `openbb_ibkr.workspace` subpackage with bundled apps.json

## [0.1.0] - 2026-05-12

### Added

- Initial open-source release
- Portfolio endpoints: positions, account summary, margin, leverage analysis
- Order/trade endpoints: open orders, completed orders, trade history
- Market data: quotes, historical bars, multi-asset support (FX, bonds, crypto, CFDs, commodities)
- Options: chain lookup, screener with Greeks, decision signals (IV/RV, skew, flow)
- Riskfolio optimization (optional): metrics, weights, risk contribution, drawdown, cumulative returns
- OpenBB provider integration: EquityQuote and EquityHistorical fetchers
- GitHub Actions CI/CD with PyPI auto-publish on tags
