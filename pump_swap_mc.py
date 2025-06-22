import requests
from dataclasses import dataclass
from typing import List, Optional

from solders.pubkey import Pubkey  # type: ignore
from solana.rpc.api import Client
from solana.rpc.commitment import Processed
from solana.rpc.types import MemcmpOpts
from construct import Padding, Struct, Int8ul, Int16ul, Int64ul, Bytes

@dataclass
class PoolKeys:
    amm: Pubkey
    base_mint: Pubkey
    quote_mint: Pubkey
    pool_base_token_account: Pubkey
    pool_quote_token_account: Pubkey
    creator: Pubkey

@dataclass
class MarketCapData:
    token_price_sol: float
    token_price_usd: float
    market_cap_usd: float

class PumpSwapMarketCap:
    PF_AMM = Pubkey.from_string("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
    WSOL = Pubkey.from_string("So11111111111111111111111111111111111111112")
    POOL_LAYOUT = Struct(
        Padding(8),
        "pool_bump" / Int8ul,
        "index" / Int16ul,
        "creator" / Bytes(32),
        "base_mint" / Bytes(32),
        "quote_mint" / Bytes(32),
        "lp_mint" / Bytes(32),
        "pool_base_token_account" / Bytes(32),
        "pool_quote_token_account" / Bytes(32),
        "lp_supply" / Int64ul,
        "coin_creator" / Bytes(32),
    )
    DIA_URL = "https://api.diadata.org/v1/assetQuotation/Solana/0x0000000000000000000000000000000000000000"

    def __init__(
        self,
        rpc_url: str,
        mint: str,
        quote_decimals: int = 9,
        total_supply: Optional[int] = None,
    ):
        self.client = Client(rpc_url)
        self.mint_str = mint
        self.mint_pubkey = Pubkey.from_string(mint)
        self.quote_decimals = quote_decimals

        if total_supply is None:
            self.total_supply = self.client.get_token_supply(
                self.mint_pubkey
            ).value.ui_amount
        else:
            self.total_supply = total_supply

        self.pool_id = self._fetch_pool_from_rpc()
        if not self.pool_id:
            raise RuntimeError(f"No pool found for mint {self.mint_str}")
        print(f"Using pool: {self.pool_id}")

        self.pool_keys = self._fetch_pool_keys()
        if not self.pool_keys:
            raise RuntimeError(f"Failed to fetch pool keys for {self.pool_id}")

        info = self.client.get_account_info_json_parsed(
            self.mint_pubkey, commitment=Processed
        ).value
        self.token_decimals = info.data.parsed["info"]["decimals"]

    def _fetch_pool_from_rpc(self) -> Optional[str]:
        base_str = self.mint_str
        quote_str = str(self.WSOL)
        filters_list: List[List[MemcmpOpts]] = [
            [
                MemcmpOpts(offset=43, bytes=base_str),
                MemcmpOpts(offset=75, bytes=quote_str),
            ],
            [
                MemcmpOpts(offset=43, bytes=quote_str),
                MemcmpOpts(offset=75, bytes=base_str),
            ],
        ]

        best: Optional[str] = None
        max_liq = 0

        for filters in filters_list:
            try:
                resp = self.client.get_program_accounts(self.PF_AMM, filters=filters)
            except Exception:
                continue

            for acct in resp.value:
                try:
                    data = acct.account.data
                    base_acc = Pubkey.from_bytes(data[139:171])
                    quote_acc = Pubkey.from_bytes(data[171:203])
                    bal_base = int(
                        self.client.get_token_account_balance(base_acc).value.amount
                    )
                    bal_quote = int(
                        self.client.get_token_account_balance(quote_acc).value.amount
                    )
                    liq = bal_base * bal_quote
                except Exception:
                    continue

                if liq > max_liq:
                    max_liq = liq
                    best = str(acct.pubkey)

        return best

    def _fetch_pool_keys(self) -> Optional[PoolKeys]:
        try:
            amm = Pubkey.from_string(self.pool_id)
            info = self.client.get_account_info_json_parsed(
                amm, commitment=Processed
            ).value
            decoded = self.POOL_LAYOUT.parse(info.data)
            return PoolKeys(
                amm=amm,
                base_mint=Pubkey.from_bytes(decoded.base_mint),
                quote_mint=Pubkey.from_bytes(decoded.quote_mint),
                pool_base_token_account=Pubkey.from_bytes(decoded.pool_base_token_account),
                pool_quote_token_account=Pubkey.from_bytes(decoded.pool_quote_token_account),
                creator=Pubkey.from_bytes(decoded.coin_creator),
            )
        except Exception:
            return None

    def _get_pool_reserves(self) -> tuple[int, int]:
        keys = self.pool_keys
        accts = [keys.pool_base_token_account, keys.pool_quote_token_account]
        resp = self.client.get_multiple_accounts_json_parsed(
            accts, commitment=Processed
        ).value
        base_amt = int(resp[0].data.parsed["info"]["tokenAmount"]["amount"])
        quote_amt = int(resp[1].data.parsed["info"]["tokenAmount"]["amount"])
        return base_amt, quote_amt

    def _get_sol_price_usd(self) -> float:
        resp = requests.get(self.DIA_URL)
        resp.raise_for_status()
        return float(resp.json()["Price"])

    def get_market_cap(self) -> MarketCapData:
        base_reserve, quote_reserve = self._get_pool_reserves()
        token_amt = base_reserve / (10 ** self.token_decimals)
        sol_amt = quote_reserve / (10 ** self.quote_decimals)

        token_price_sol = sol_amt / token_amt
        sol_usd = self._get_sol_price_usd()
        token_price_usd = token_price_sol * sol_usd
        market_cap_usd = token_price_usd * self.total_supply

        return MarketCapData(
            token_price_sol=token_price_sol,
            token_price_usd=token_price_usd,
            market_cap_usd=market_cap_usd,
        )

if __name__ == "__main__":
    rpc_url = "https://api.mainnet-beta.solana.com"
    mint_str = ""
    pump_swap_mc = PumpSwapMarketCap(rpc_url, mint_str)
    mc_data = pump_swap_mc.get_market_cap()

    print(f"Token price (SOL): {mc_data.token_price_sol:.10f} SOL")
    print(f"Token price (USD): ${mc_data.token_price_usd:.10f}")
    print(f"Market cap (USD):  ${mc_data.market_cap_usd:,.2f}")
