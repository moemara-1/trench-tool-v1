# Trench Tool V2 Provider And GitHub Research Matrix

Date: 2026-05-24

This document maps the RAVN/BBB feature catalog to free or cheap APIs, credible GitHub/open-source components, and the parts V2 must build itself.

## 2026-05-24 Implementation Batch

Implemented and deployed side-by-side to `trench-v2-backend`:

- DexScreener command market provider for `/scan`, `/analyze`, `/og`, and `/simulate` token metadata.
- Honeypot.is risk provider enabled by default as the free EVM security source.
- GoPlus risk provider gated behind `GOPLUS_API_KEY`.
- Composite risk aggregation with taxes, honeypot, malicious-contract, liquidity-lock, and liquidity-pull fields.
- Etherscan V2 log client gated behind `ETHERSCAN_API_KEY`.
- Alchemy wallet-history client using `alchemy_getAssetTransfers` when an RPC URL/API key exists.
- Uniswap V2 `PairCreated`, Uniswap V3 `PoolCreated`, PancakeSwap V2 `PairCreated`, and ERC-20 `Approval` event decoders.
- Wallet profile builder from transfer history for fresh/dormant/normie/team-wallet foundations.
- `/v2/features` readiness metadata: `live_producer`, `provider_ready`, `needs_api_key`, `blocked_external_source`, `contract_ready`, or `planned`.

## 2026-05-24 Key Wiring And Holder Batch

V1 env was re-checked for provider keys without exposing values. It had Helius, Solana RPC, and BSC RPC values, but no Etherscan or Moralis key. V2 already had Alchemy and now has Etherscan/Moralis wired.

Implemented:

- Moralis ERC-20 token owners client for ETH/Base/BSC.
- Conservative holder cluster builder from Moralis owner rows.
- Scanner integration so `/scan` and `/analyze` can attach holder clusters when `MORALIS_API_KEY` is configured.
- `/v2/scan` now returns `holder_clusters` so the API exposes wallet/supply evidence.

The Moralis holder provider intentionally does not invent team/insider labels from holder percentage alone. It labels obvious contracts as `contract_holder`, known owner/entity labels as evidence, and large EOAs as `large_holder` until wallet-history/funding graph evidence exists.

Still blocked on external wiring/source confirmation:

- Holder/bundle acceleration needs `MORALIS_API_KEY` or a paid/usable holder API path.
- Deeper EVM wallet features need `ALCHEMY_API_KEY` or `ETHERSCAN_API_KEY`.
- V2 Solana ownership of dormant/fresh/SNS/migrations needs usable Helius quota or an alternate Solana provider.
- Boop/Bags/BelieveApp deploy/claim features need official program/API sources before production decoding.

## Bottom Line

There is no reliable open-source drop-in replacement for RAVN/BBB-style alerts. GitHub has small wallet trackers, token scanners, and protocol SDKs, but the core edge is not packaged anywhere credible:

- wallet history classification
- holder clustering
- team/insider/snipe supply attribution
- dormant/fresh/normie quality scoring
- launch replay and missed-winner review
- low-noise Telegram routing

Use public APIs and official SDKs for raw data. Build the scoring, clustering, dedupe, replay, and alert decisions in V2.

## Research Sources

### Free Or Cheap APIs Worth Wiring

| Source | Cost profile | Use in V2 | Notes |
| --- | --- | --- | --- |
| [DexScreener API](https://docs.dexscreener.com/api/reference) | Free, no key | New token profiles, pair metadata, liquidity, volume, price, FDV | Already used by V2 live EVM freshies/deploys. Good discovery layer, not enough for wallet intelligence. |
| [GeckoTerminal API](https://api.geckoterminal.com/docs/index.html) | Free public API | Pool lookup, token pools, OHLCV, network/dex fallback | Best backup when DexScreener misses or lags. |
| [Alchemy Transfers API](https://www.alchemy.com/docs/reference/alchemy-getassettransfers) | Free tier then paid | EVM wallet history, token transfers, launch/wallet replay | Strong default for ETH/Base. Use BSC only if the account has that chain enabled; otherwise use Etherscan V2/Blockscout for BSC. |
| [Etherscan API V2](https://docs.etherscan.io/etherscan-v2) | Free tier then paid | Multichain txs, token transfers, logs, contract source, top holders | V2 docs say one API key can address many chains via `chainid`, including BSC and Base. Good cheap fallback. |
| [Etherscan logs endpoint](https://docs.etherscan.io/api-reference/endpoint/getlogs) | Free tier then paid | PairCreated, PoolCreated, Approval logs, factory backfills | Useful for catch-up jobs, not ideal as only real-time source. |
| [Blockscout API](https://eth.blockscout.com/api-docs) | Free per supported explorer, Pro for multichain | Explorer fallback for txs/token transfers/contracts | Good fallback where public Blockscout instances exist. Must handle chain-specific availability. |
| [GoPlus Token Security API](https://docs.gopluslabs.io/reference/tokensecurityusingget_1) | Public/free-ish, rate limits apply | EVM honeypot/security flags, taxes, mint/owner/proxy/blacklist, LP holder risk | First security layer for `/analyze`. |
| [Honeypot.is IsHoneypot](https://docs.honeypot.is/ishoneypot) | Public with API key option | EVM buy/sell simulation, honeypot, taxes, pre-liquidity simulation | Pair with GoPlus. Good for `/analyze` and `/simulate`. |
| [Moralis Token API](https://moralis.mintlify.app/data-api/universal/token/overview) | Free tier then paid | Holder lists, token owners, token analytics, wallet data | Use if holder snapshots via logs are too slow. Likely the cheapest way to accelerate bundle/holder features. |
| [Helius DAS/API](https://www.helius.dev/docs/das-api) | Free tier then paid | Solana assets by owner, parsed transactions, wallet histories | Existing V1 relies on Helius. V2 needs backoff and per-key quotas before enabling Solana health. |
| [Bitquery Solana APIs](https://docs.bitquery.io/) | Limited free, paid for volume | Solana balance updates, holder history, pump/Raydium streams | Candidate when Helius quota cannot support replay or holder scans. |
| [Jupiter Recurring/DCA API](https://dev.jup.ag/docs/recurring) | Public docs | Jupiter DCA orders/events | Use official API/docs for DCA feature. Avoid guessing program IDs from random repos. |
| [ENS resolution docs](https://docs.ens.domains/resolution/) | RPC only | ENS/Base ENS reverse and primary name checks | Build directly over RPC or Universal Resolver. |
| [Uniswap v2 architecture docs](https://developers.uniswap.org/docs/protocols/v2/concepts/architecture) | Public docs/contracts | ETH/Base pair launch detection | Factory/pair contracts are the correct source for launch log indexers. |
| [Uniswap v3 overview/deployments](https://developers.uniswap.org/docs/protocols/v3/overview) | Public docs/contracts | ETH/Base pool launch detection | Use v3 factory deployments/logs for PoolCreated-based launch tracking. |
| [PancakeSwap Factory v2 docs](https://docs.pancakeswap.finance/japanese/code/smart-contracts/pancakeswap-exchange/factory-v2) | Public docs/contracts | BSC pair launch/migration detection | Documents BSC factory address and `PairCreated` event. |

### GitHub/Open Source Worth Reusing

| Repo | Verdict | Use |
| --- | --- | --- |
| [SolanaNameService/sns-sdk](https://github.com/SolanaNameService/sns-sdk) | Use | Official SNS SDK monorepo. Use for SOL SNS buys/reverse lookup instead of inventing SNS parsing. |
| [streamflow-finance/timelock-crate](https://github.com/streamflow-finance/timelock-crate) | Use carefully | Official archived Streamflow community/timelock program source. Useful for lock account parsing. |
| [streamflow-finance/streamflow-program](https://github.com/streamflow-finance/streamflow-program) | Reference only | Deprecated Rust program, useful for historical decoding but not a modern dependency. |
| [crytic/slither](https://github.com/crytic/slither) | Use offline/async | Mature Solidity/Vyper static analyzer. Good for malicious-contract evidence, not real-time pings. |
| [ConsenSysDiligence/mythril](https://github.com/ConsenSysDiligence/mythril) | Optional offline | Symbolic EVM analyzer. Heavy; use for deeper async contract review, not hot path. |
| [wmalgo/whale-watcher](https://github.com/wmalgo/whale-watcher) | Reference only | Simple EVM wallet Telegram tracker. Useful pattern, not enough for Trench V2. |
| [S-Amine/token-scan](https://github.com/S-Amine/token-scan) | Do not depend | Low activity/low stars. Reference at most. |
| GitHub `rugcheck`, `gmgnai`, scraped APIs | Avoid for core | Many are scrapers, trading bots, or fragile unofficial APIs. Do not build production alerts on them. |

## System Pieces V2 Must Build

| Piece | Why APIs/GitHub are not enough |
| --- | --- |
| `WalletProfile` builder | APIs can return txs, but V2 must label fresh/dormant/normie/bot/team/insider from history. |
| `HolderCluster` engine | Holder APIs do not reliably identify common funders, split-wallet users, team wallets, or bundle clusters. |
| `RiskReport` aggregator | GoPlus/Honeypot/Slither disagree; V2 needs one normalized risk verdict and evidence list. |
| `SignalScore` model | RAVN/BBB-style value is quality filtering, not volume. The score must combine liquidity, wallet quality, risk, novelty, and replay performance. |
| `AlertDecision` engine | Telegram routing, cooldowns, daily caps, dedupe, and topic creation must stay tied to working producers. |
| Replay store | Public APIs do not decide whether the bot missed winners or spammed false positives. Store normalized events and outcomes locally. |

## Feature Matrix

| Feature | Providers/APIs | GitHub/open source | Build in V2 | Recommendation |
| --- | --- | --- | --- | --- |
| `ravnview_scan` | DexScreener, GeckoTerminal, Alchemy, Etherscan V2, GoPlus, Honeypot, Helius | Slither optional | Token scan aggregator, normalized holder/supply report | Build provider-backed scanner. |
| `ravnview_analyze` | GoPlus, Honeypot.is, Etherscan source, Alchemy logs | Slither, Mythril async | Delayed honeypot/liquidity-pull/malicious-contract verdict | Implement next for EVM. |
| `ravnview_track` | Alchemy transfers/logs, Etherscan, Helius | wmalgo/whale-watcher as reference | Team wallet watch targets, pre-live sell/transfer alerts | Build own watch engine. |
| `ravnview_og` | DexScreener, GeckoTerminal, Etherscan, GoPlus, Honeypot | None strong | Old-tax suppression, pre-bond candidate filter, pool type V2/V3/V4 | Build on top of scanner. |
| `ravnview_simulate` | Honeypot force simulation, GoPlus, Alchemy logs, Helius | None strong | Pre-live decision report, sniper/team/funder checks | Build after `/analyze`. |
| `ravn_bundle_supply` | Moralis holders, Etherscan top holders, Alchemy transfer graph, Helius token accounts | None strong | Supply clusterer, common-funder graph, team/insider/sniper totals | Build core differentiator. |
| `sol_dormants` | Helius parsed tx/history, Bitquery Solana history if needed | None strong | Wallet-age plus prior-token quality labels | Keep V1 until V2 Solana indexer exists. |
| `sol_low_mc_big_freshies` | Helius, DexScreener/GeckoTerminal, Bitquery | None strong | Fresh-wallet quality scoring and low-MC thresholding | Build with replay before topic. |
| `sol_freshies_sells` | Helius transactions, token account balances | None strong | Detect fresh wallets exiting, exclude noise wallets | Build after SOL wallet profiles. |
| `sol_semi_dormants` | Helius/Bitquery wallet history | None strong | Semi-dormant definition and success history filter | Build after dormants. |
| `sol_semi_dormants_sells` | Helius/Bitquery | None strong | Semi-dormant exit detector | Build after semi-dormants. |
| `sol_sns_buys` | Helius DAS, SNS reverse lookups | SolanaNameService/sns-sdk | SNS ownership/name enrichment and buy detector | Use official SNS SDK. |
| `sol_vanish_buys` | Helius wallet history, token balances | None strong | Vanish-wallet definition, reappearance/buy signal | Need local definition from replay. |
| `sol_vanish_sells` | Helius wallet history, token balances | None strong | Exit detector for vanished wallets | Build only with replay proof. |
| `sol_bundles` | Helius token accounts, transfer graph, Bitquery holder/balance updates | None strong | Common-funder/bundle clusterer | Build, no credible repo. |
| `sol_patterns` | Helius, DexScreener, local replay DB | None strong | Pattern definitions from historical winners/false positives | Build after replay store. |
| `sol_freshies_wizard` | Helius, DexScreener, local replay DB | None strong | Composite fresh-wallet score and explainable reasons | Build after basic freshies. |
| `sol_migrations_tracker` | Helius, Raydium/Pump/Jupiter sources, DexScreener fallback | Protocol docs/program IDs | Detect migration from bonding/launch venue to tradable pool | Build with official program sources. |
| `sol_old_migrations` | Same as migrations plus token age | Protocol docs/program IDs | Old migration filter and liquidity/volume quality gates | Build after migrations. |
| `sol_dormant_deploys` | Helius deploy/program transactions | None strong | Deployer wallet history and dormant deploy scoring | Build after SOL wallet profiles. |
| `sol_jupiter_dca` | Jupiter Recurring/DCA API/docs, Helius | Jupiter docs | DCA order/event parser and quality filters | Use official Jupiter docs/API. |
| `sol_liquidity_inflows` | Helius transfers, Raydium/Orca/Jupiter pool events, DexScreener | Protocol docs | Detect meaningful liquidity additions, not tiny noise | Build with strict thresholds. |
| `sol_boop_deploys` | Helius, Boop official source once confirmed | None confirmed | Protocol-specific deploy watcher | Block until official program/source is confirmed. |
| `sol_bags_claims` | Helius, Bags official source once confirmed | None confirmed | Claim-event decoder and quality scoring | Block until official program/source is confirmed. |
| `sol_believeapp_deploys` | Helius, BelieveApp official source once confirmed | None confirmed | Deploy watcher and wallet-quality scoring | Block until official program/source is confirmed. |
| `eth_freshies` | DexScreener live now, Alchemy logs for real-time, GeckoTerminal fallback | None strong | Fresh-wallet qualification and replay tuning | Already live from DexScreener; improve with Alchemy. |
| `eth_big_freshies` | DexScreener, Alchemy, Etherscan | None strong | Buy-size/fresh-wallet scoring | Already live; add wallet proof. |
| `eth_low_mc_freshies` | DexScreener, GeckoTerminal, Alchemy | None strong | Low-MC quality filter | Already live; tune by replay. |
| `eth_dormants` | Alchemy transfers, Etherscan txlist/tokentx | wmalgo reference only | Dormant-wallet detector with prior-token history | Build after wallet profile index. |
| `eth_low_mc_dormants` | Alchemy, Etherscan, DexScreener | None strong | Dormant plus low-MC and risk gates | Build after ETH dormants. |
| `eth_bundles` | Moralis holders, Etherscan top holders, Alchemy graph | None strong | Team/insider/sniper supply clusterer | Build; Moralis likely useful. |
| `eth_ens_buys` | ENS Universal Resolver, Alchemy logs/transfers | ENS docs, no repo needed | Reverse-name enriched buy detector | Build directly. |
| `eth_normie_buys` | Alchemy wallet history, Etherscan | None strong | Normie wallet classifier and buy detector | Build with replay labels. |
| `eth_difference_checker` | Alchemy/Etherscan histories, DexScreener snapshots | None strong | Compare wallets/token launches and flag deltas | Build as analysis command. |
| `eth_unique_contracts` | Alchemy logs, Etherscan contract source, GoPlus | Slither optional | Contract novelty/creator history detector | Build after launch indexer. |
| `eth_pre_approvals` | Alchemy/Etherscan Approval logs | None strong | Approval watcher for known routers/spenders and risky patterns | Build early, cheap. |
| `eth_launches_tracker` | Uniswap V2 PairCreated, Uniswap V3 PoolCreated, DexScreener fallback | Uniswap docs | Factory log indexer and launch outcome tracking | Build early. |
| `base_freshies` | DexScreener live now, Alchemy/Base RPC, GeckoTerminal | None strong | Fresh-wallet qualification | Already live; improve with Alchemy. |
| `base_low_mc_freshies` | DexScreener live now, Alchemy/Base RPC | None strong | Low-MC quality filter | Already live; tune by replay. |
| `base_dormants` | Alchemy/Base transfers, Etherscan V2/BaseScan, Blockscout | None strong | Dormant wallet classifier on Base | Build after EVM wallet indexer. |
| `base_low_mc_dormants` | Same plus DexScreener/GeckoTerminal | None strong | Low-MC dormant scoring | Build after Base dormants. |
| `base_deploys` | DexScreener live now, Alchemy factory logs | None strong | Deploy quality scoring | Already live; improve with log source. |
| `base_curated_deploys` | Alchemy logs, DexScreener, known Base launch protocols | None strong | Curated deploy source list and creator-score gates | Build after base deploys. |
| `base_pre_approvals` | Alchemy Approval logs, Etherscan V2/BaseScan | None strong | Base approval watcher | Build with ETH pre-approvals. |
| `base_ens_buys` | ENS L2/reverse docs, Alchemy Base transfers | ENS docs | Base reverse-name enriched buy detector | Build with ETH ENS buys. |
| `bnb_freshies` | DexScreener live now, Etherscan V2/BscScan, GeckoTerminal | None strong | Fresh-wallet qualification | Already live from DexScreener; add BSC explorer/RPC. |
| `bnb_big_freshies` | DexScreener live now, Etherscan V2/BscScan | None strong | Big fresh buy scoring | Already live; add wallet proof. |
| `bnb_low_mc_freshies` | DexScreener live now, GeckoTerminal, BscScan | None strong | Low-MC scoring | Already live; tune by replay. |
| `bnb_dormants` | Etherscan V2/BscScan, Alchemy if BSC enabled, Blockscout fallback | None strong | Dormant BSC wallet classifier | Build after EVM wallet indexer. |
| `bnb_big_dormants` | Same plus buy-size thresholds | None strong | Big dormant buy detector | Build after BNB dormants. |
| `bnb_semi_dormants` | Same plus recency windows | None strong | Semi-dormant detector | Build after BNB dormants. |
| `bnb_migrations_tracker` | PancakeSwap PairCreated, DexScreener/GeckoTerminal, BscScan logs | PancakeSwap docs | Migration/pair watcher with quality gates | Build after BSC log source. |
| `bnb_bundles` | Moralis holders, Etherscan V2/BscScan top holders, transfer graph | None strong | BSC holder/supply clusterer | Build with ETH bundles. |

## Build Order

1. EVM security core: GoPlus + Honeypot + Etherscan source + Slither async, powering `/analyze`.
2. EVM log indexer: Uniswap/Pancake factory logs, Approval logs, and launch outcome store.
3. EVM wallet profile indexer: Alchemy/Etherscan histories cached locally, powering dormants/freshies/normies/ENS.
4. Holder and bundle analyzer: Moralis/Etherscan holder snapshots plus local transfer graph clustering.
5. Solana provider recovery: Helius key rotation/backoff, normalized parsed transaction cache, optional Bitquery only if free tier is insufficient.
6. Solana protocol features: SNS SDK, Streamflow parser, Jupiter Recurring/DCA, then Boop/Bags/BelieveApp only after official program IDs/sources are confirmed.
7. Replay and review loop: every alert stores inputs, score, delivery topic, and later ATH/drawdown so thresholds improve from evidence.

## Implementation Warnings

- Do not create Telegram topics for this matrix until the producer is live and has delivered a test alert.
- Do not store full provider responses in Upstash. The existing 100 MB max record warning means V2 should store normalized rows, chunked wallet histories, and compressed fixtures only.
- Do not depend on unofficial scraped GMGN/RugCheck-style repos for production. They break quietly and create false confidence.
- Keep V1 SOL producers running until V2 Solana can prove fresh data flow without Helius 429 loops.
- Prefer cheap/free APIs first, but design provider interfaces so Moralis/Bitquery/Covalent-style paid upgrades can be swapped in without changing alert logic.

## Exact Access To Wire Next

| Priority | Secret/access | Why |
| --- | --- | --- |
| 1 | GoPlus API access if needed, or permission to use unauthenticated public endpoint | EVM `/analyze` security layer. |
| 2 | Honeypot.is API key if you have one | EVM buy/sell simulation and tax/honeypot confidence. |
| 3 | Etherscan V2 API key | Cheap multichain tx/log/holder/contract fallback for ETH/Base/BSC. |
| 4 | Confirm whether the existing Alchemy app has Base and BSC enabled | Determines whether we use Alchemy for all EVM chains or only ETH/Base. |
| 5 | Moralis free-tier key | Speeds up holder/bundle analysis; otherwise we build slower holder snapshots from logs. |
| 6 | Fresh Helius keys with plan/quota visibility | Needed before V2 owns SOL features. |
| 7 | Optional Bitquery free trial/key | Only if Helius cannot support SOL holder/history workloads cheaply. |
