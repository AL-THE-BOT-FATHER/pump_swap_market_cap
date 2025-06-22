# PumpSwapMarketCap

A Python module for discovering the highest-liquidity WSOL trading pool for any Solana token, parsing on-chain AMM data, and computing token price & market cap in SOL and USD.

## Features

- Scan all PumpSwap AMM pools to pick the one with the most liquidity for your token vs. WSOL
- Decode on-chain AMM account data into structured PoolKeys
- Fetch live token & SOL reserves directly from the pool
- Retrieve current SOL→USD price from the DIA Oracle
- Calculate:
  - Token price in SOL
  - Token price in USD
  - Token market cap in USD

- Dataclasses
  - PoolKeys — holds all the on-chain pool account addresses and mints
  - MarketCapData — cleanly returns token_price_sol, token_price_usd, and market_cap_usd from get_market_cap()
