import json
from typing import Any
from abc import abstractmethod
from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState

class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )

        # We truncate state.traderData, trader_data, and self.logs to the same max. length to fit the log limit
        max_item_length = (self.max_log_length - base_length) // 3

        print(
            self.to_json(
                [
                    self.compress_state(state, self.truncate(state.traderData, max_item_length)),
                    self.compress_orders(orders),
                    conversions,
                    self.truncate(trader_data, max_item_length),
                    self.truncate(self.logs, max_item_length),
                ]
            )
        )

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing.symbol, listing.product, listing.denomination])

        return compressed

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]

        return compressed

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append(
                    [
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.buyer,
                        trade.seller,
                        trade.timestamp,
                    ]
                )

        return compressed

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sugarPrice,
                observation.sunlightIndex,
            ]

        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        compressed = []
        for arr in orders.values():
            for order in arr:
                compressed.append([order.symbol, order.price, order.quantity])

        return compressed

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value

        return value[: max_length - 3] + "..."





# general class for a product
class Product_Strategy:
    def __init__(self):
        self.productSymbol: Symbol
        self.limit: int
    @abstractmethod
    def makeOrders(self, state: TradingState) -> list[Order]:
        pass



# General class for a product traded with a market making strategy
class mm_Product_Strategy(Product_Strategy):
    def __init__(self):
        super().__init__()
        # Adjustable Market making parameters
        # - spread: The spread between the buy/sell and the fair price
        # - custom_limit: The position that the trader considers extreme
        # - liquidate_val: The price the trader utilizes to liquidate their position
        self.custom_limit: int
        self.spread: int
        self.liquidate_val: int
        
    # Calculate the fair value of the product and return
    @abstractmethod
    def fairValue(self, state: TradingState) -> int:
        pass
    # Generalize purchases of Market making based off adjustable parameters:
    # - custom_limit: The position that the trader considers extreme
    # - spread: The spread between the buy/sell and the fair price
    # - fair_price: the price the trader values the product at
    # - liquidate_val: The price the trader utilizes to liquidate their position
    def makeOrders(self, state: TradingState) -> list[Order]:
        # create list of orders to be returned
        orders = []
        # Get available orders for the product
        order_depth = state.order_depths[self.productSymbol]
        # Get the current position on9 the product
        current_position = 0 if self.productSymbol not in state.position else state.position[self.productSymbol]
        
        # Obtain the fair price of the product
        fair_price = self.fairValue(state)
        
        # Adjust fair buy and sell price from true fair price
        if current_position <= -self.custom_limit:
            fair_buy_price = fair_price + self.liquidate_val
        else: 
            fair_buy_price = fair_price - self.spread
        if current_position >= self.custom_limit:
            fair_sell_price = fair_price - self.liquidate_val
        else:
            fair_sell_price = fair_price + self.spread
        
        # ~ Potential change to be tested in the future: ~
        #   Adjust order depending on the current position on the product
        
        # Buy out available fair sell order (Note vol in sell is negative)
        for price, volume in order_depth.sell_orders.items():
            if price <= fair_buy_price and current_position - volume <= self.limit:
                orders.append(Order(self.productSymbol, price, -volume))
                current_position -= volume
                logger.print("BUY", str(-volume) + "x", price)
    
        # Sell out available fair buy orders
        for price, volume in order_depth.buy_orders.items():
            if price >= fair_sell_price and current_position - volume >= -self.limit:
                orders.append(Order(self.productSymbol, price, -volume))
                current_position -= volume
                logger.print("SELL", str(volume) + "x", price)

        # Re-Adjust fair buy and sell price from true fair price
        if current_position <= -self.custom_limit:
            fair_buy_price = fair_price + self.liquidate_val
        else: 
            fair_buy_price = fair_price - self.spread
        if current_position >= self.custom_limit:
            fair_sell_price = fair_price - self.liquidate_val
        else:
            fair_sell_price = fair_price + self.spread
        
        # Make own orders outside available
        if current_position <= -self.custom_limit: # If we are too short buy at fair val
            orders.append(Order(self.productSymbol, fair_buy_price, -current_position))
            logger.print("BUY", str(abs(current_position)) + "x", fair_buy_price)
        elif current_position >= self.custom_limit: # If we are too long sell at fair val
            orders.append(Order(self.productSymbol, fair_sell_price, -current_position))
            logger.print("SELL", str(abs(current_position)) + "x", fair_buy_price)
        else: # Else trade at fair spread
            # Buy at fair buy price
            orders.append(Order(self.productSymbol, fair_buy_price, self.custom_limit))
            logger.print("BUY", str(abs(self.custom_limit)) + "x", fair_buy_price)
            # Sell at fair sell price
            orders.append(Order(self.productSymbol, fair_sell_price, -self.custom_limit))
            logger.print("SELL", str(abs(self.custom_limit)) + "x", fair_sell_price)
        return orders
            

    
class Rainforest_Resin_Strategy(mm_Product_Strategy):
    def __init__(self):
        super().__init__()
        self.productSymbol = "RAINFOREST_RESIN"
        self.limit = 50
        # Set the adjustable parameters for the strategy
        self.spread = 2
        self.custom_limit = 15
        self.liquidate_val = 0

    # Static fair value of 10000
    def fairValue(self, state: TradingState) -> int:
        return 10000


strategies = dict[Symbol: Product_Strategy]()
strategies["RAINFOREST_RESIN"] = Rainforest_Resin_Strategy()
logger = Logger()

class Trader:
    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        
        result = {}
        conversions = 0
        trader_data = ""
        
        for product in state.market_trades.keys():
            if product not in strategies:
                continue
            orders = strategies[product].makeOrders(state)
            result[product] = orders
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data
