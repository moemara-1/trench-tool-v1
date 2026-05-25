# Trench Tool V2 RAVN Feature Audit

Generated from local Obsidian clippings in `C:\Users\User\Documents\Obsidian Vault\Clippings`, local RAVN notes in `C:\Users\User\Documents\Obsidian Vault\RAVN`, the public RAVN GitBook, and the BBB GitBook pages. Last implementation update: 2026-05-24.

## Source Inventory

| Source | Product signal |
| --- | --- |
| `RAVN Docs.md` | RAVNView scanner, low-noise alerts, all-chain direction, holder/supply analysis. |
| `Post by @UniswapVillain on X 9.md` | Eliminate noise, SOL/BSC scanner, web mirror, on-chain plus social data, daily review. |
| `Post by @UniswapVillain on X.md` | `/simulate` for pre-live sniper scans. |
| `Post by @UniswapVillain on X 1.md` | `/analyze` for delayed honeypots, liquidity pulls, malicious ETH contracts. |
| `Post by @UniswapVillain on X 2.md` | `/track` team wallets selling even before token is live on-chain. |
| `Post by @UniswapVillain on X 3.md` | `/og` suppresses older ETH tax tokens. |
| `Post by @UniswapVillain on X 4.md` | Bundle logic should count team/insiders, not only first-block bundles; dormant wallet definition. |
| `Post by @UniswapVillain on X 5.md` | Detect team-control supply and tax-reflection abuse. |
| `Post by @UniswapVillain on X 6.md` | `/og` includes ETH pre-bond tokens and pool type V2/V3/V4. |
| `Post by @UniswapVillain on X 7.md` | ETH bundle scanning and ETH alert support. |
| `Post by @UniswapVillain on X 8.md` | BSC scanner support. |
| `Post by @debestfk on X.md` | Dormant tracking can find old social/narrative revivals. |
| GitBook Overview | RAVNView plus Alerts; low-noise, useful information, holder drilldowns. |
| GitBook RAVNView | Top-holder transaction history, wallet labels, warnings for bad trends. |
| GitBook Bundle Scanner | Supply distribution across team/insiders, snipers, multi-wallet users. |
| GitBook Process | 24/7 launch logging, 100+ wallet/dev/holder data points, backtesting and filter evolution. |
| GitBook FAQ | Web mirror exists, alerts should not be auto-traded, user cap/noise discipline. |
| BBB GitBook root | Supported suite index across Solana, Ethereum, Base, and BSC/BNB. |
| BBB Ethereum suite | Freshies, big/low-MC freshies, dormants, low-MC dormants, bundles, ENS buys, normie buys, difference checker, unique contracts, pre-approvals, launches tracker. |
| BBB Base suite | Freshies, low-MC freshies, dormants, low-MC dormants, deploys, curated deploys, pre-approvals, ENS buys. |
| BBB BSC suite | Freshies, big/low-MC freshies, dormants, big dormants, semi-dormants, migrations tracker. |
| BBB Solana suite | Dormants, low-MC big freshies, freshies sells, semi-dormants sells, SNS, vanish buys/sells, migrations, old migrations, dormant deploys, Jupiter DCA, liquidity inflows, Boop deploys, Bags claims, BelieveApp deploys. |

## Public Docs Page Inventory

The public BBB page crawl returned these concrete suite pages. Placeholder/editor/demo GitBook pages are not treated as signal functions unless the page corresponds to a named alert in the source inventory.

| Suite | Pages considered |
| --- | --- |
| Solana | `bags-claims`, `dormant-deploys`, `freshies-sells`, `migrations-tracker`, `old-migrations`, `semi-dormants-sells`, `vanish-sells`, plus placeholder/demo pages: `editor`, `images-and-media`, `integrations`, `interactive-blocks`, `markdown`, `openapi`. |
| Ethereum | `bundles`, `difference-checker`, `dormants`, `ens-buys`, `freshies`, `launches-tracker`, `normie-buys`, `pre-approvals`, `unique-contracts`. |
| Base | `base-ens-buys`, `curated-deploys`, `deploys`, `dormants`, `freshies`, `pre-approvals`. |
| BSC/BNB | `freshies`, `migrations-tracker`, plus generated markdown placeholders. |

The public RAVN page crawl returned `ravnview`, `ravn-process-under-the-hood`, `overview/alerts-and-channels-past-performance`, `overview/membership-options`, `overview/the-ideal-ravn-user`, `about-the-creators`, and `faqs`. The implementation-relevant pages are RAVNView, process/backtesting, alerts/channels, and FAQ/web mirror behavior; membership and creator biography pages do not add bot functions.

## 2026-05-23 Topic Rollout

The running V1 bot is left online. Active SOL topics were preserved after Telegram send/delete verification. Two stale BSC V1 topic IDs were diagnosed as broken (`message thread not found`) and disabled on disk so the next V1 restart does not keep routing into dead threads.

V2 now has a data-backed topic registry in `trench_v2.telegram.topics` and a docs-backed feature catalog in `trench_v2.core.feature_catalog`. The side-by-side API exposes both:

| Endpoint | Purpose |
| --- | --- |
| `/v2/topics` | Shows every planned Telegram topic, its env key, and whether it is configured in the running process. |
| `/v2/features` | Shows every RAVN/BBB-backed feature contract, thresholds, source, and topic env key. |

New Telegram topics created and verified for V2:

| Chain | Topics |
| --- | --- |
| SOL | Existing active SOL topics were aliased into V2 where possible; new V2-only topics were created for `SOL Scan`, `SOL Track`, `SOL Simulate`, `Freshies Sells (SOL)`, `Semi-Dormants (SOL)`, `Semi-Dormants Sells (SOL)`, `Big Dormants (SOL)`, `SOL Low MC Big Freshies`, `Pre-Migration Dormants (SOL)`, `Freshies Inflow (SOL)`, `Freshies Spike (SOL)`, `Vanish Sells (SOL)`, `Old Migrations (SOL)`, `Dormant Deploys (SOL)`, `Jupiter DCA (SOL)`, `Liquidity Inflows (SOL)`, `Boop Deploys (SOL)`, `Bags Claims (SOL)`, `BelieveApp Deploys (SOL)`, `Feedback`. |
| ETH Mainnet | `ETH Mainnet`, `ETH Analyze`, `ETH OG`, `ETH Simulate`, `ETH Freshies`, `ETH Big Freshies`, `ETH Low MC Freshies`, `ETH Dormants`, `ETH Low MC Dormants`, `ETH Bundles`, `ETH ENS Buys`, `ETH Normie Buys`, `ETH Difference Checker`, `ETH Unique Contracts`, `ETH Pre-Approvals`, `ETH Launches Tracker` |
| Base | `Base`, `Base Analyze`, `Base Simulate`, `Base Freshies`, `Base Low MC Freshies`, `Base Dormants`, `Base Low MC Dormants`, `Base Deploys`, `Base Curated Deploys`, `Base Pre-Approvals`, `Base ENS Buys`, `Base Bundles` |
| BNB/BSC | `BNB`, `BNB Analyze`, `BNB Freshies`, `BNB Big Freshies`, `BNB Low MC Freshies`, `BNB Dormants`, `BNB Big Dormants`, `BNB Semi-Dormants`, `BNB Bundles`, `BNB Migrations Tracker` |

## 2026-05-24 Topic Cleanup And Live Signals

The first rollout created every planned topic before every producer existed, which made Telegram look broken. The cleanup pass deletes placeholder topics and keeps only destinations with a live producer. Docs-backed features stay in `/v2/features`, but they do not get Telegram topics until a provider-backed producer exists.

| Result | Count / status |
| --- | --- |
| Deleted empty/non-producing topics | 50 |
| Live topic plan | SOL Freshies, SOL Dormants, SOL Migrations Tracker, ETH Freshies, ETH Big Freshies, ETH Low MC Freshies, Base Freshies, Base Low MC Freshies, Base Deploys, BNB Freshies, BNB Big Freshies, BNB Low MC Freshies |
| V2 live worker | Running |
| V2 worker source | DexScreener latest token profiles plus pair data |
| V2 worker routes | ETH Freshies, ETH Big Freshies, ETH Low MC Freshies, Base Freshies, Base Low MC Freshies, Base Deploys, BNB Freshies, BNB Big Freshies, BNB Low MC Freshies |
| Quality controls | Minimum quality score 70/100, liquidity/market-cap/volume/buy-pressure gates, 5 minute polling, 2 sends max per cycle, 30 high-quality sends max per day |
| Current limitation | SOL V1 keeps only active SOL producers. V2 Solana provider health is disabled by default until a V2 Solana producer is shipped; V1 remains the Solana runtime health source. |

## Topic Policy

Telegram topics are not a roadmap. A topic exists only when the bot can currently send useful signals to it.

| Kept | Reason |
| --- | --- |
| SOL Freshies | V1 live counter is producing. |
| SOL Dormants | V1 live counter is producing. |
| SOL Migrations Tracker | V1 live counter is producing. |
| ETH/Base/BNB Freshies variants | V2 DexScreener worker is producing quality-scored EVM alerts. |
| Base Deploys | V2 DexScreener worker is producing fresh Base deploy alerts. |

| Removed until provider-backed | Reason |
| --- | --- |
| SOL Bundles, Patterns, Freshies Wizard, SNS, Vanish, DEV Held, Good Token creators, Socials, Strong launches, Strong floor, Streamflow locks | Live V1 counters were zero, or the implementation lacks a valid provider/program source. |
| ETH/Base/BNB Dormants, ENS buys, bundles, normie buys, unique contracts, pre-approvals, migrations, analyze/simulate command topics | Cataloged from BBB/RAVN docs, but no active V2 producer yet. |

## Feature Matrix

| ID | Requirement | Current V2 status | Evidence / gap | Implementation direction |
| --- | --- | --- | --- | --- |
| F01 | Support SOL, ETH, BSC, Base command scanning. | Partial | `Chain` enum and command parser exist. No real providers. | Keep chain-neutral contracts; add provider adapters behind protocols. |
| F02 | Token scanner returns useful holder data within seconds. | Partial | `TokenScan.holder_clusters` exists but lacks wallet drilldown fields. | Add holder wallet behavior model and supply report. |
| F03 | Show exact wallets behind team/insider/sniper/bundle percentages. | Partial | `HolderCluster.wallets` exists as strings only. | Add cluster kinds and wallet profile labels/evidence. |
| F04 | Analyze top-holder transaction history. | Missing provider integration | V1 has Solana holder scanner; V2 has no history provider. | Add provider contract for wallet histories; do not block model/test work. |
| F05 | Wallet profile includes holdings, PnL, funding source, previous coins, purchase size tendencies, activity date, past performance, hold time, token count. | Missing | Existing `WalletProfile` only has age, tx count, funding source, labels. | Extend `WalletProfile` with nullable fields and behavior labels. |
| F06 | Filter misleading wallets: MEV bots, high-volume wallets, team/PnD wallets. | Missing | No V2 wallet labeler. | Add deterministic wallet behavior labeler. |
| F07 | Dormant wallets are only positive when history is not mostly rugs/manipulated launches. | Missing | V1 dormant logic is age-only; docs say history matters. | Add dormant quality labels using prior successful/rugged buys. |
| F08 | Bundle logic counts team/insider control beyond first few blocks. | Partial | V2 has `bundle_supply_percent`; no category aggregation. | Add supply distribution analyzer by cluster kind/label. |
| F09 | Separate team/insiders, snipers, multi-wallet terminal/bot users, unrelated holders. | Missing | Only freeform cluster labels. | Add `HolderClusterKind` and category totals. |
| F10 | Detect high team control and reflection/tax abuse. | Partial | Risk has taxes; no reflection/team-control coupling. | Add risk reasons and supply-policy scoring. |
| F11 | `/analyze` catches delayed honeypots, liquidity pulls, malicious contracts. | Partial | Risk model has honeypot/liquidity lock/taxes. | Add delayed honeypot and malicious contract flags to risk model. |
| F12 | `/og` suppresses older ETH tax tokens. | Missing | `find_og()` returns placeholder scan. | Add OG candidate filter and tests. |
| F13 | `/og` includes ETH pre-bond tokens and pool type V2/V3/V4. | Missing | No pre-bond or pool type fields. | Add `is_pre_bonded`, `pool_type`, and format output. |
| F14 | `/simulate` can scan pre-live tokens for sniper decisions. | Skeleton | Command exists, but returns normal scan plus placeholder. | Add simulation report contract after provider data exists. |
| F15 | `/track` monitors team-wallet sells before live trading. | Skeleton | Watchlist tracks address only. | Add watch target type and team-wallet sell event contracts. |
| F16 | Alerts scan new launches automatically and stay low-noise. | Present for EVM freshies/deploys | V2 worker uses DexScreener discovery plus quality gates. | Add more provider-backed signal families only after each one can prove useful data flow. |
| F17 | Alerts average 10-30 premium pings/day. | Present | `signal_daily_cap=30`, `signal_min_quality=70`, and max 2 sends per cycle. | Tune thresholds from replay results, not by adding volume. |
| F18 | Alerts route to specific channels/topics by signal type. | Present for live topics | `/v2/topics` exposes only producer-backed topics. | Add topics only as new producers ship. |
| F19 | Alerts are not auto-trading and should support judgment. | Present | Commands do not buy/sell and tests assert no trade command. | Keep as hard invariant. |
| F20 | Track every launch and update ATH/performance metrics for backtesting. | Missing | No V2 replay store. | Add persistence/replay in later provider phase. |
| F21 | Combine on-chain and social data. | Partial | `social_score` exists; V1 has social services. | Add V2 social provider contract later. |
| F22 | Web mirror should mirror Telegram. | Deferred | V2 API exists; no web UI/auth. | Build after Telegram/provider core. |

## Immediate Implementation Scope

This pass implements the feature contracts and deterministic policy pieces that can be tested without provider keys:

1. Wallet behavior fields and labels.
2. Holder cluster kinds and supply distribution summaries.
3. OG candidate filtering for older tax tokens and pre-bond/pool metadata.
4. Low-noise alert policy with daily cap, cooldown, and dedupe.
5. Telegram scan formatting that exposes supply and OG/pre-bond fields when present.

Provider-backed work remains blocked on real provider wiring and secrets, but the contracts should make that work mechanical instead of vague.
