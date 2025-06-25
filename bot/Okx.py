import logging
import os
import requests

import pandas as pd
from okx.Account import AccountAPI
from okx.MarketData import MarketAPI
from okx.Trade import TradeAPI
from okx.PublicData import PublicAPI

# Отключаем INFO-логи для всех сторонних библиотек, которые могут логировать HTTP-запросы
'''loggers_to_silence = [
    "httpx", "httpcore.http11", "httpcore.http2", "httpcore.connection",
    "httpcore.proxy", "hpack.table", "hpack.hpack"
]

for logger_name in loggers_to_silence:
    logging.getLogger(logger_name).setLevel(logging.WARNING)
class RemoveHttpRequests(logging.Filter):
    """Фильтр, убирающий логирование запросов HTTP Request"""
    def filter(self, record):
        return "HTTP Request" not in record.msg.lower()  # Фильтруем регистронезависимо

clOrdId = 'log'
class RemoveHttpRequests(logging.Filter):
    """Фильтр, убирающий сообщения с 'HTTP Request'"""
    def filter(self, record):
        return "http request" not in record.msg.lower()  # Фильтруем регистронезависимо'''

# Удаляем все обработчики логгера, чтобы избежать конфликтов
#for handler in logging.root.handlers[:]:
#    logging.root.removeHandler(handler)

# Настроим логирование
#logging.basicConfig(
#    filename='bot.log',
#    level=logging.INFO,
#   format='%(asctime)s - %(levelname)s - %(message)s'
#)
# Отключаем INFO-логи для всех сторонних библиотек
#logging.getLogger("requests").setLevel(logging.WARNING)
#logging.getLogger("urllib3").setLevel(logging.WARNING)
# Создание логгера и добавление фильтра
#logger = logging.getLogger()
#logger.addFilter(RemoveHttpRequests())

# Функция-обертка для print, записывающая сообщения в лог-файл
#def print(*args, **kwargs):
#    message = ' '.join(map(str, args))  # Объединяем аргументы в строку
#    logger.info(message)  # Записываем в лог-файл
#    print(message, **kwargs)  # Оригинальный print

logger = logging.getLogger('maxicocode-yt')
bot_token = '7939368628:AAH34mcSW2n-UXKHTeuhd_-iwA49SgSKCJI'
chat_id = '509843392'
old_short_posId = 0
old_long_posId = 0

class Okx:
    """
    Класс OKX реализует логику взаимодействия с биржей ОКХ
    торговой логики в нем нет
    """
    def __init__(self):
        logger.info(f"{os.getenv('NAME', 'Anon')} OKX Auth loaded")

        # для определения позиции
        self.position_id = "MaxicoCodeSWAP"

        # загрузка значения из переменных окружения,
        # чтобы при изменении окружения после запуска бота, бот продолжал нормально работать
        self.symbol = os.getenv('SYMBOL')
        self.qty = float(os.getenv('QTY'))

        # На данный момент SDK python-okx предоставляет отдельные классы к каждой секции
        # вместо единого клиента (хотя он в SDK есть, поэтому, надеюсь такой расклад не надолго)
        # чтобы не дублировать параметры для каждого класса - в конструкторе инициализирую словарь настроек
        self.params = dict(
            domain='https://www.okx.com',
            flag=os.getenv('IS_DEMO', '1'),
            api_key=os.getenv('API_KEY', '1'),
            api_secret_key=os.getenv('SECRET', '1'),
            passphrase=os.getenv('PASSPHRASE', '1'),
            debug=False
        )

    def get_instrument (self):
        r = PublicAPI(**self.params).get_instruments(instType = "SWAP" , instId = self.symbol)
        ctVal = float(r.get('data', [])[0].get('ctVal')) 
        return ctVal
    
    def close_prices(self, instId, timeframe='1m', limit = 50):
        """
        Возвращаю серию цен закрытия (close) Pandas для обработки в библиотеке ta
        :param timeframe:
        :param instId:
        :param limit:
        :return:
        """
        klines = MarketAPI(**self.params).get_candlesticks(instId, limit=limit, bar=timeframe).get('data', [])
        klines.reverse()
        #print(klines)
        return pd.Series([float(e[4]) for e in klines])

    def check_permissions(self):
        """
        Простой запрос к состоянию баланса Аккаунта
        для проверки прав доступа предоставленных ключей,
        если ключи не правильные выкинет ошибку

        :raises: OkxAPIException
        :return:
        """
        r = AccountAPI(**self.params).get_account_balance()
    
    def get_last_price (self, timeframe='1m', limit = 1):
        klines = MarketAPI(**self.params).get_candlesticks(instId = self.symbol, limit=limit, bar=timeframe).get('data', [])
        #klines.reverse()
        #return pd.Series([float(e[4]) for e in klines])
        for e in klines:
            res = float(e[4]) 
        #print(res)
        return res
    
    def get_last_pnl(self): # получаем pnl последней закрытой позиции
        position = AccountAPI(**self.params).get_positions_history(instType="SWAP", instId = self.symbol, limit = 1)
        pnl = 0
        if position["code"] == "0":        
            #print(position)
            symbol = position.get('data', [])[0].get('uly')
            print(symbol)
            pnl = round(float(position.get('data', [])[0].get('realizedPnl')), 2)
            print(pnl)                        
        return [pnl, symbol]
    
    def GetOrderId(self,side):
        list_orders = TradeAPI(**self.params).get_order_list(instType = "SWAP" , instId = self.symbol)
        order_id = 0        
        clOrdId = ''
        if list_orders.get('data', []) != []:                        
            a = list_orders.get('data', [])            
            for el in a:                
                if el.get('posSide') == side:
                   order_id = el.get('ordId')
                   clOrdId = el.get('clOrdId')                                       
        return [order_id, clOrdId]
    def GetAlgoOrderId(self,side): # ищем algo ордера               
        res = TradeAPI(**self.params).order_algos_list(instType = "SWAP" , instId = self.symbol, ordType = "limit" )     # 
        algoId = 0  
        algoClOrdId = ''      
        if res.get('data', []) != []:                
            a = res.get('data', [])
            for el in a:                
                if el.get('algoId') != ''  and el.get('posSide') == side:                    
                    algoId = el.get('algoId')                                    
                    algoClOrdId = el.get('algoClOrdId')
        return [algoId, algoClOrdId]
        
    def GetBalance(self):
        balance = AccountAPI(**self.params).get_account_balance(ccy="USDT")
        return balance
                


    def GetMarkPrice(self):        
        res = PublicAPI(**self.params).get_mark_price(instType = "SWAP" , instId = self.symbol)
        #print(r)
        markPrice = float(res.get('data', [])[0].get('markPx'))           
        return markPrice

    def place_market_order(self, side, posSide,sz): # размещаем market order
        result = TradeAPI(**self.params).place_order(instId=self.symbol,tdMode="isolated",side=side,posSide=posSide, ordType="optimal_limit_ioc",sz=sz)
        #print("размещаем",posSide, "маркет ордер")
        return result       
    
    def place_hedge_order(self, side, posSide,sz): # размещаем market order c TP         
        result = TradeAPI(**self.params).place_order(instId=self.symbol,tdMode="isolated",side=side,posSide=posSide, ordType="optimal_limit_ioc",sz=sz, clOrdId = "hedge")        
        print("hedge result",result)
        res = float(result.get('data', [])[0].get('sCode'))
        ordId = result.get('data', [])[0].get('ordId')
        #print("размещаем",posSide, " хедж маркет ордер")
        if res == 0:                                 
            print(posSide,"хедж ордер", ordId, " установлен")          
        else: print(result) 

        return [ res, ordId ]
    
    
    def place_order(self, side, posSide, sz, px, clOrdId): # размещаем limit order
    #def place_order(self, side, posSide, sz, px, tpTriggerPx, slTriggerPx): # размещаем limit order
        #attachAlgoOrds = [{"tpOrdPx":tpTriggerPx, "tpTriggerPx":tpTriggerPx}]
        #result = TradeAPI(**self.params).place_order(instId=self.symbol,tdMode="isolated",side=side,posSide=posSide, ordType="limit", sz=sz, px=px, attachAlgoOrds = attachAlgoOrds)
        result = TradeAPI(**self.params).place_order(instId=self.symbol,tdMode="isolated",side=side,posSide=posSide, ordType="limit",clOrdId=clOrdId, sz=sz, px=px)
        #print("размещаем лимитный",posSide, "ордер")
        return result      
    
    def place_merge_order(self, side, posSide, sz, px, clOrdId): # размещаем merge limit order    
        result = TradeAPI(**self.params).place_order(instId=self.symbol,tdMode="isolated",side=side,posSide=posSide, ordType="limit",clOrdId=clOrdId,sz=sz, px=px)        
        return result      
    def place_merge_algo_order(self, side, posSide, sz, px, algoClOrdId): # размещаем merge limit order    
        result = TradeAPI(**self.params).place_algo_order(instId=self.symbol,tdMode="isolated",side=side,posSide=posSide, ordType="conditional",algoClOrdId=algoClOrdId,closeFraction=1,sz=sz, px=px)        
        return result
    
    def place_algo_tp_sl_order(self, side, posSide, tpTriggerPx, slTriggerPx, algoClOrdId): # размещаем algo TP SL order
        sCode = 0
        res = TradeAPI(**self.params).place_algo_order(instId=self.symbol, tdMode='isolated',reduceOnly = True, side=side, ordType='oco', posSide = posSide, algoClOrdId=algoClOrdId, closeFraction=1, tpTriggerPx='{:10.11f}'.format (tpTriggerPx), tpOrdPx=-1, slTriggerPx = '{:10.11f}'.format (slTriggerPx), slOrdPx=-1)
        if res["code"] == "1":                    
            sCode = float(res.get('data', [])[0].get('sCode'))
        return [res, sCode]    
    def place_algo_tp_order(self, side, posSide, tpTriggerPx, algoClOrdId): # размещаем algo TP order
        sCode = 0
        res = TradeAPI(**self.params).place_algo_order(instId=self.symbol, tdMode='isolated',reduceOnly = True, side=side, ordType='conditional', posSide = posSide, algoClOrdId=algoClOrdId, closeFraction=1, tpTriggerPx='{:10.11f}'.format (tpTriggerPx),tpOrdPx=-1)
        if res["code"] == "1":                    
            sCode = float(res.get('data', [])[0].get('sCode'))
        return [res, sCode]    
    def place_algo_sl_order(self, side, posSide, slTriggerPx, algoClOrdId): # размещаем algo SL order
        sCode = 0
        res = TradeAPI(**self.params).place_algo_order(instId=self.symbol, tdMode='isolated',reduceOnly = True, side=side, ordType='conditional', posSide = posSide, algoClOrdId=algoClOrdId, closeFraction=1, slTriggerPx=slTriggerPx,slOrdPx=-1)
        if res["code"] == "1":                    
            sCode = float(res.get('data', [])[0].get('sCode'))
        return [res, sCode]    
    
    def cancel_algo_order(self, algoId ): # удаление trigger ордера        
        algo_order = [{"instId": self.symbol, "algoId": algoId}]      
        del_algos = TradeAPI(**self.params).cancel_algo_order(algo_order)        
        return del_algos
    
    def get_algo_order_id(self,side): # ищем trigger ордера               
        res = TradeAPI(**self.params).order_algos_list(instId=self.symbol, ordType = "trigger" )     # 
        algoId = 0        
        if res.get('data', []) != []:                
            a = res.get('data', [])
            for el in a:                
                if el.get('algoId') != ''  and el.get('posSide') == side:                    
                    algoId = el.get('algoId')                                    
        return algoId
        
    def Amend_order (self, ordId, ord_algo_id, new_order_price,new_tp_price,newTpSz):  # обновляем limit order
        attachAlgoOrds = [{"attachAlgoId":ord_algo_id, "tpOrdPx":new_tp_price, "tpTriggerPx":new_tp_price, "sz":newTpSz}]
        #print("new_order_price",new_order_price)
        #print("new_tp_price   ",new_tp_price)
        AmendResult = TradeAPI(**self.params).amend_order(instId=self.symbol, ordId=ordId, newPx=new_order_price, attachAlgoOrds=attachAlgoOrds )                
        return AmendResult
    
    def cancel_order (self,ordId):
        CancelResult = TradeAPI(**self.params).cancel_order(instId=self.symbol, ordId = ordId)
        return CancelResult
    
    def get_pos_tp(self,posSide): # ищем TP 
        sl = TradeAPI(**self.params).order_algos_list(instId=self.symbol, ordType = "conditional" )     # замени ordType на 'oco' если ставишь стоплоссы  conditional
        #print("order_algos_list", sl)
        algoId = 0        
        tpTriggerPx = 0
        sz = 0
        if sl.get('data', []) != []:                      
            a = sl.get('data', [])
            #print(a)
            for el in a:                
                if el.get('algoId') != ''  and el.get('posSide') == posSide:                    
                    algoId = el.get('algoId')                
                    if el.get('tpTriggerPx') != '':
                        tpTriggerPx = float(el.get('tpTriggerPx'))
                    sz = el.get('sz')   # размер позиции
            #        print(posSide, "TP ордер", algoId, "TP Px", tpTriggerPx )                   
        return [algoId,tpTriggerPx, sz]
    
    def get_pos_tp_sl(self,posSide): # ищем TP SL
        sl = TradeAPI(**self.params).order_algos_list(instId=self.symbol, ordType = "oco" )     # замени ordType на 'oco' если ставишь стоплоссы  conditional
        #print("order_algos_list", sl)
        algoId = 0        
        tpTriggerPx = 0
        slTriggerPx = 0
        sz = 0
        if sl.get('data', []) != []:                      
            a = sl.get('data', [])
            #print(a)
            for el in a:                
                if el.get('algoId') != ''  and el.get('posSide') == posSide:                    
                    algoId = el.get('algoId')                
                    if el.get('tpTriggerPx') != '':
                        tpTriggerPx = float(el.get('tpTriggerPx'))
                    if el.get('slTriggerPx') != '':
                        slTriggerPx = float(el.get('slTriggerPx'))
                    sz = el.get('sz')   # размер позиции
            #        print(posSide, "TP ордер", algoId, "TP Px", tpTriggerPx )                   
        return [algoId,tpTriggerPx, slTriggerPx, sz]
    
    def new_algos_tp_px(self, algoId, new_algos_tp_px): # переставление TP 
        new_sl_tp_algos = TradeAPI(**self.params).amend_algo_order(instId=self.symbol, algoId = algoId, newTpTriggerPx = new_algos_tp_px, newTpOrdPx= -1)        
        return new_sl_tp_algos
    
    def new_algos_tp_sz(self, algoId, newSz): # размер TP 
        new_sl_tp_algos = TradeAPI(**self.params).amend_algo_order(instId=self.symbol, algoId = algoId, newSz = newSz)        
        return new_sl_tp_algos
    
    def is_short_position(self):        # Ищем открытую Шорт позицию                         
        positions=AccountAPI(**self.params).get_positions(instType="SWAP",instId=self.symbol)
        #print("positions",positions)
        short = False
        posId = 0
        posPx = 0        
        upl = 0
        pos = 0
        fee = 0
        notionalUsd = 0
        cTime = 0
        if positions.get('data', []) != []:
            a = positions.get('data', [])
            #print(a)
            for el in a:
                if el.get('adl') != '':                                            
                    if el.get('posSide') == 'short' :                    
                        posPx = float(el.get('avgPx'))
                        posId = el.get('posId')
                        upl = round(float(el.get('upl')), 2 )
                        pos = float(el.get('pos'))               # количество контрактов в позиции
                        notionalUsd = round(float(el.get('notionalUsd')), 2)
                        fee = round(float(el.get('fee')), 2)
                        cTime = float(el.get('cTime'))
                        #print("найдена Шорт позиция", posId, "с ценой", posPx , cTime)
                        short = True
        else: 
            
            print("Шорт позиция не обнаружена")
        return  [short, posId, posPx, upl, pos, fee, notionalUsd, cTime]    
    
    def is_long_position(self):        # Ищем открытую Лонг позицию                         
        positions=AccountAPI(**self.params).get_positions(instType="SWAP",instId=self.symbol)        
        long = False
        posId = 0
        posPx = 0
        upl = 0        
        pos = 0
        fee = 0
        notionalUsd = 0
        cTime = 0
        if positions.get('data', []) != []:
            a = positions.get('data', [])
            for el in a:                
                if el.get('adl') != '':                                  
                    if el.get('posSide') == 'long' :                    
                        posPx = float(el.get('avgPx'))
                        posId = el.get('posId')
                        upl = round(float(el.get('upl')), 2)
                        pos = float(el.get('pos'))
                        fee = round(float(el.get('fee')), 2)
                        notionalUsd = round(float(el.get('notionalUsd')), 2)
                        cTime = float(el.get('cTime'))
                        #print("найдена Лонг позиция", posId, "с ценой", posPx, cTime)                    
                        long = True
        else:             
            print("Лонг позиция не обнаружена")
        return  [long, posId, posPx, upl, pos, fee, notionalUsd, cTime]

    def get_upl(self):
        uplPos=AccountAPI(**self.params).get_positions(instType="SWAP",instId=self.symbol) 
        if uplPos.get('data', []) != []:
            a = uplPos.get('data', [])
            for el in a:                
                if el.get('adl') == '1':                                  
                    upl = float(el.get('upl'))                    
        return upl

    def get_short_pos_tp_sl(self): # ищем TP/SL               
        sl = TradeAPI(**self.params).order_algos_list(ordType = "oco" )                        
        algoId = 0
        if sl.get('data', []) != []:                            
            a = sl.get('data', [])
            for el in a:
                if el.get('algoId') != '' and el.get('posSide') == 'short':        
                    algoId = el.get('algoId')                
                    print("SL/TP шорт ордер найден", algoId )        
        return algoId
    def get_short_pos_tp(self): # ищем TP/SL               
        sl = TradeAPI(**self.params).order_algos_list(ordType = "conditional" )                        
        algoId = 0
        if sl.get('data', []) != []:                            
            a = sl.get('data', [])
            for el in a:
                if el.get('algoId') != '' and el.get('posSide') == 'short':        
                    algoId = el.get('algoId')                
                    print("TP шорт ордер найден", algoId )        
        return algoId
    
    def get_long_pos_tp_sl(self): # ищем TP/SL               
        sl = TradeAPI(**self.params).order_algos_list(ordType = "oco" )     # замени ordType на 'oco' если ставишь стоплоссы
        algoId = 0        
        if sl.get('data', []) != []:                
            a = sl.get('data', [])
            for el in a:                
                if el.get('algoId') != ''  and el.get('posSide') == 'long':                    
                    algoId = el.get('algoId')                
                    print("SL/TP лонг ордер найден", algoId )                   
        return algoId
    
    def get_long_pos_tp(self): # ищем TP/SL               
        tp = TradeAPI(**self.params).order_algos_list(ordType = "conditional" )     # замени ordType на 'oco' если ставишь стоплоссы
        algoId = 0        
        if tp.get('data', []) != []:                
            a = tp.get('data', [])
            for el in a:                
                if el.get('algoId') != ''  and el.get('posSide') == 'long':                    
                    algoId = el.get('algoId')                
                    print("TP лонг ордер найден", algoId )                   
        return algoId
        
    def set_pos_tp_sl(self,side,posSide,sl_px,tp_px): # установка TP/SL ордера        
        sl_tp = TradeAPI(**self.params).place_algo_order(instId=self.symbol, tdMode='isolated', side=side, ordType='oco', posSide=posSide,closeFraction=1, slTriggerPx=sl_px,slOrdPx=-1,tpTriggerPx=tp_px,tpOrdPx=-1)        
        return sl_tp 
    def set_pos_tp(self,side,posSide,tp_px):           # установка TP ордера
        tp = TradeAPI(**self.params).place_algo_order(instId=self.symbol, tdMode='isolated', side=side, ordType='conditional', posSide=posSide,closeFraction=1,tpTriggerPx=tp_px,tpOrdPx=-1)
        return tp
    def set_pos_sl(self,side,posSide,sl_px): # установка SL ордера        
        sl = TradeAPI(**self.params).place_algo_order(instId=self.symbol, tdMode='isolated', side=side, ordType='conditional', posSide=posSide,closeFraction=1, slTriggerPx=sl_px,slOrdPx=-1)        
        return sl 
    
    
    def new_algos_tp_sl_px(self, algoId, new_algos_tp_px, new_algos_sl_px): # переставление TP и SL ближе к цене                
        new_sl_tp_algos = TradeAPI(**self.params).amend_algo_order(instId=self.symbol, algoId = algoId, newTpTriggerPx = new_algos_tp_px, newTpOrdPx= -1, newSlTriggerPx = new_algos_sl_px, newSlOrdPx= -1)        
        return new_sl_tp_algos
    
    def del_sl_tp_algos(self, algoId ): # удаление SL/TP          
        algo_orders = [{"instId": self.symbol, "algoId": algoId}]      
        del_sl_tp_algos = TradeAPI(**self.params).cancel_algo_order(algo_orders)        
        return del_sl_tp_algos

    def get_last_pnl(self): # получаем pnl последней закрытой позиции
        position = AccountAPI(**self.params).get_positions_history(instType="SWAP",instId=self.symbol,limit = 1)
        if position["code"] == "0":        
            #print(position)
            pnl = float(position.get('data', [])[0].get('pnl'))
            #print(pnl)
            fee = round(float(position.get('data', [])[0].get('fee')), 2)
            #print(fee)
            abs_pnl = pnl + fee
            #print(abs_pnl)
            posId = position.get('data', [])[0].get('posId')
        return [pnl, fee, abs_pnl, posId]
    def get_last_pos(self): # получаем данные последней закрытой позиции
        position = AccountAPI(**self.params).get_positions_history(instType="SWAP",instId=self.symbol,limit = 1)
        if position["code"] == "0":        
            pnl = float(position.get('data', [])[0].get('pnl'))                     # прибыль
            fee = round(float(position.get('data', [])[0].get('fee')), 2)           # комиссия
            abs_pnl = pnl + fee                                                     # прибыль с учетом комиссии (-)
            posId = position.get('data', [])[0].get('posId')                        # ID позиции
            closeAvgPx = float(position.get('data', [])[0].get('closeAvgPx'))       # цена закрытия
            closeTotalPos = float(position.get('data', [])[0].get('closeTotalPos')) # размер позиции
            direction = position.get('data', [])[0].get('direction')                # направление позиции
        return [pnl, fee, abs_pnl, posId, closeAvgPx, closeTotalPos, direction]
    
    def get_last_fee(self): # получаем pnl последней закрытой позиции
        position = AccountAPI(**self.params).get_positions_history(instType="SWAP",instId=self.symbol,limit = 1)
        if position["code"] == "0":        
            fee = float(position.get('data', [])[0].get('fee'))
            #print(fee)
        return fee
    def send_telegramm_message(self,message):        
        send_message_url = f'https://api.telegram.org/bot{bot_token}/sendMessage' 
        payload = {'chat_id': chat_id,'text': message} 
        response = requests.post(send_message_url, data=payload)
        print(response.json())
        return False