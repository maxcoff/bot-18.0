import logging
import os
from dotenv import load_dotenv
from time import sleep
import ta.trend
from bot.Okx import Okx
import time

import requests
import pandas as pd
import numpy as np

#from decimal import Decimal, ROUND_CEILING

logger = logging.getLogger('maxicode')

# глобальные переменные сюда    
tpSTriggerPx = 0
tpLTriggerPx = 0
short_limit_Flag = 1 
long_limit_Flag = 1
OldShortOrderPrice = 0
OldLongOrderPrice = 0
last_pnl = 0
last_hedge = 0
last_volatility = 0
short_pos = 0
long_pos = 0





class Bot(Okx):
    def __init__(self):
        super(Bot, self).__init__()
        env_file = ".env"
        
         # загрузка значения из переменных окружения,
        # чтобы при изменении окружения после запуска бота, бот продолжал нормально работать
        self.timeout = int(os.getenv('TIMEOUT', 10))
        self.timeframe = os.getenv('TIMEFRAME', '1m')
        self.clOrdId = str(os.getenv('CLIORDID', 'clOrdId'))
        self.symbol = os.getenv('SYMBOL')
        self.ema_fast = int(os.getenv('EMA_FAST', '1'))
        self.ema_slow = int(os.getenv('EMA_SLOW', '12'))
        self.sma_fast = int(os.getenv('SMA_FAST', '3'))
        self.sma_slow = int(os.getenv('SMA_SLOW', '7'))
        self.round_contract = int(os.getenv('ROUND_CONTRACT', ''))
        self.qty = float(os.getenv('QTY'))
        self.hedge_multiple = float(os.getenv('HEDGE_MULTIPLE'))   
        self.hedge_multiple_reserv = float(os.getenv('HEDGE_MULTIPLE_RESERV'))   
        self.min_volatility = float(os.getenv('MIN_VOLATILITY', '4'))

        self.fee_open = float(os.getenv('FEE_OPEN'))        
        self.fee_close = float(os.getenv('FEE_CLOSE'))        
        self.Ep = float(os.getenv('EP'))     

        self.stop_flag = int(os.getenv('STOP', 0))

        self.max_sum = float(os.getenv('MAX_SUM'))
        self.TP_sz = float(os.getenv('TP', '0.4'))
        #self.qTP = int(os.getenv('qTP'))
        self.hedgeSL = float(os.getenv('HEDGE_SL'))
        self.limit_sz = float(os.getenv('LIMIT', '0.4'))
        print ("переменные окружения загружены")

        
        
    
    def sma(self):  # Серия Пандас с ценами закрытия, в обратном (для ОКХ) порядке
        close = self.close_prices(self.symbol, self.timeframe)        
        slow = ta.trend.sma_indicator(close, self.ema_slow).values # Расчет простых скользящих средних, более свежие значение в конце списка 
        return slow
    def is_cross(self):
        """
        Определяю пересечение простых скользящих средних
        Возвращает:
         0 - если на текущем баре пересечения нет
         1 - быстрая пересекает медленную снизу вверх, crossout, сигнал на покупку
        -1 - быстрая пересекает медленную сверху вниз, crossover, сигнал на продажу
        :return:
        """
        # Серия Пандас с ценами закрытия, в обратном (для ОКХ) порядке
        close = self.close_prices(self.symbol, self.timeframe)

        # Расчет простых скользящих средних,
        # более свежие значение в конце списка
        # нам нужны 2 последних значения
        fast = ta.trend.ema_indicator(close, self.sma_fast).values
        slow = ta.trend.ema_indicator(close, self.sma_slow).values
        
        #if   fast[-1] > slow[-1] and fast[-2] < slow[-2]: r = 1 ; print ("sma_trend" , r) # crossover быстрая снизу вверх 
        #elif fast[-1] < slow[-1] and fast[-2] > slow[-2]: r = -1 ; print ("sma_trend" , r) # crossunder быстрая свверху вниз
        if   fast[-1] > slow[-1] : r = 1  # crossover быстрая снизу вверх 
        elif fast[-1] < slow[-1] : r = -1 # crossunder быстрая свверху вниз        

        if r != 0: logger.info(f"{r} = now {fast[-1]:.6f} / {slow[-1]:.6f}, prev {fast[-2]:.6f} / {slow[-2]:.6f}")
        return r
    
        # Функция для получения исторических данных с OKX
    def fetch_ohlcv(self, symbol, timeframe='1m', limit=45):
        url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar={timeframe}&limit={limit}"
        response = requests.get(url)
        data = response.json()

        if 'data' in data and data['data']:
            ohlcv = pd.DataFrame(data['data'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'currencyVolume', 'tradingVolume','Kline'])
            ohlcv = ohlcv[::-1]
            # Преобразование данных
            ohlcv['timestamp'] = pd.to_datetime(pd.to_numeric(ohlcv['timestamp']) / 1000, unit='s')
            ohlcv[['open', 'high', 'low', 'close', 'volume']] = ohlcv[['open', 'high', 'low', 'close', 'volume']].apply(pd.to_numeric)
            return ohlcv
        else:
            print("Ошибка: API OKX не вернул данные")
            return None

    # Функция для расчёта Close-to-Close Volatility
    def calculate_volatility(self, data, period=30):
        try:
            if data is None or len(data) < period:
                print("Недостаточно данных для расчёта волатильности")
                return None
            data['returns'] = np.log(data['close'] / data['close'].shift(1))  # Логарифмическая доходность
            data['volatility'] = data['returns'].rolling(window=period).std() * np.sqrt(period) * 100 * 2.95  # Стандартное отклонение * корень периода
            data = data.reset_index(drop=True)

            return data[['volatility']]
        except Exception as e:
            logger.error(str(e)) 
        
    
    def volatility(self):
        data = self.fetch_ohlcv(self.symbol)    # Получение данных свечей                        
        volatility_data = self.calculate_volatility(data).reset_index(drop=True) # Расчёт волатильности        
        last_volatility = round(volatility_data['volatility'].iloc[-1],2)        # выборка и округление
        return last_volatility    
        
    def check(self):       
        
        try:
            print("---",self.clOrdId,"---")                     
            #print ("self.ema_fast", self.ema_fast)      

            last_price = self.get_last_price()
            #print (last_price)
            
            slow = self.sma()     
            
            short_ord = self.GetOrderId('short')                 # ищем шорт ордер            
            long_ord = self.GetOrderId('long')                   # ищем лонг ордер        

            short_id = short_ord [0]
            long_id = long_ord [0]            
            #print("short_id",short_id)
            #print("long_id",long_id)

            shortPos = 0
            longPos = 0
            global short_pos
            short_pos = self.is_short_position() 
            global long_pos
            long_pos = self.is_long_position()                                 
            shortPos = short_pos[0]                     # наличие позиции
            longPos = long_pos [0]                      # наличие позиции
            SposPrice = short_pos[2]                    # цена открытия позиции
            LposPrice = long_pos[2]                     # цена открытия позиции
            short_upl = short_pos[3]                    # upl позиции
            #print ("short upl",short_upl)                
            long_upl  = long_pos[3]                     # upl позиции
            #print ("long upl",long_upl)                
            s_pos = short_pos[4]                        # количество контрактов в позиции (нужно для закрытия по маркету)
            l_pos = long_pos [4]                        # количество контрактов в позиции                        
            short_sum = short_pos [6]                   # сумма позиции в USD
            long_sum = long_pos [6]                     # сумма позиции в USD
            short_cTime = short_pos[7]                  # время создания
            long_cTime = long_pos[7]                    # время создания
            

            Short_clOrdId = self.clOrdId + "short"
            Long_clOrdId = self.clOrdId + "long"
            
            #sma_trend = self.is_cross() # отключил
            #print ("sma_trend", sma_trend)
            S_algo_order = self.get_pos_tp('short')                                     # проверяем есть ли TP             
            S_algoOrdId = S_algo_order [0]     
            S_algoTPpx = S_algo_order [1]    
            if S_algoOrdId == 0: 
                S_algo_order = self.get_pos_tp_sl('short')
                S_algoOrdId = S_algo_order [0]     
                S_algoTPpx = S_algo_order [1]     
                S_algoSLpx = S_algo_order [2]     
            print ("S_algoOrdId",S_algoOrdId)
            L_algo_order = self.get_pos_tp('long') 
            L_algoOrdId = L_algo_order [0]
            L_algoTPpx = L_algo_order [1]
            if L_algoOrdId == 0:
                L_algo_order = self.get_pos_tp_sl('long') 
                L_algoOrdId = L_algo_order [0]            
                L_algoTPpx = L_algo_order [1]
                L_algoSLpx = L_algo_order [2]
            print ("L_algoOrdId",L_algoOrdId)

            
            
            global tpSTriggerPx
            global tpLTriggerPx
            global short_limit_Flag 
            global long_limit_Flag
            global OldShortOrderPrice
            global OldLongOrderPrice            
            global last_hedge
            

            '''# расчет ТP в режиме хеджирования
            if shortPos == True or longPos == True:
                newSTpTriggerPx  = SposPrice - SposPrice / 100 * (LposPrice * 100 / SposPrice - 100 + self.TP_sz)
                newLTpTriggerPx = LposPrice + LposPrice / 100 * (abs(SposPrice * 100 / LposPrice - 100) + self.TP_sz)'''
                     
                # ХЕДЖИ
            
            
             # если сумма лубой из позиций выше пороговой, то множитель хеджа = HEDGE_MULTIPLE_RESERV
            hedge_mult = self.hedge_multiple
            if long_sum >= self.max_sum or short_sum >= self.max_sum:
                hedge_mult = self.hedge_multiple_reserv

            #y = self.Ep * (1+(s_pos + l_pos)/self.qty/100*3)
            #y = round(self.Ep * (1+(s_pos + l_pos)/self.qty/100/10),2)
            #print ('y',y)
            #print ("Ep",self.Ep)

            if longPos == True and last_hedge >= 0 :
                #  установка хеджирующей шортовой позиции                                
                if long_upl <= self.hedgeSL :           # crossout                                                            and sma_trend < 0
                    # запрет  лимитных ордеров                                                     
                    short_limit_Flag = 0 ; long_limit_Flag = 0                           # запрет лимитных ордеров
                    if short_id !=0 : CancelOrder = self.cancel_order(short_id)    # снимаем лимитный шорт ордер
                    if long_id !=0 : CancelOrder = self.cancel_order(long_id)    # снимаем лимитный лонг ордер                        

                    if shortPos == False :
                        res = self.place_hedge_order('sell', 'short', round(l_pos * hedge_mult,self.round_contract))
                        print (res) 

                        # запрос цены SposPrice                        
                        short_pos = self.is_short_position() 
                        SposPrice = short_pos[2]                    # цена открытия позиции
                        s_pos = short_pos[4]                        # кол-во контрактов
                        
                        #newSTpTriggerPx = (S_C_short * s_pos * SposPrice - l_pos * LposPrice) / (S_C_short * s_pos - l_pos) # формула расчета баланса позиций breakeven
                        #newSTpTriggerPx = (l_pos * LposPrice * (1 + 0.0002) - s_pos * SposPrice * (1 + 0.0002)) / (l_pos * (1 - 0.0005) - s_pos * (1 + 0.0005)) # формула расчета баланса позиций breakeven
                        newSTpTriggerPx = (l_pos * LposPrice * (1 + self.fee_open) - s_pos * SposPrice * (1 - self.fee_open)) / (l_pos * (1 - self.fee_close) - s_pos * (1 + self.fee_close) - round(self.Ep * (1+(s_pos + l_pos)/self.qty/100/10),2)) # формула расчета баланса позиций breakeven
                        
                        
                        print ("newSTpTriggerPx ",newSTpTriggerPx)
                        print ("last_price",last_price)
                        #print ("SposPrice",SposPrice)
                        #print ("LposPrice",LposPrice)
                        
                        
                        S_tp = self.place_algo_tp_order('buy', 'short', newSTpTriggerPx, Short_clOrdId) # устанавливаем TP на шорт
                        #SSlTriggerPx = LposPrice + LposPrice /100*self.TP_sz               # вычисляем цену SL
                        #S_tp = self.place_algo_tp_sl_order('buy', 'short', newSTpTriggerPx, SSlTriggerPx, Short_clOrdId )  # устанавливаем SL TP на шорт                 
                        print ("TP шорта",S_tp)
                        if S_tp[1] == 51277:
                                print ("закрываем ТР по маркету 51277", s_pos )
                                close_order = self.place_market_order('buy', 'short', s_pos)
                                print ("close TP order", close_order)
                        else:
                            del_algo = self.cancel_algo_order(L_algoOrdId) # чистим лонг
                            print ("чистим лонг",del_algo)
                            LTpTriggerPx = LposPrice + LposPrice /100*self.TP_sz               # вычисляем цену TP                                                                    
                            l_SL = self.place_algo_tp_sl_order('sell', 'long', LTpTriggerPx, newSTpTriggerPx, Long_clOrdId)  # устанавливаем SL TP на лонг
                            print ("TP/SL лонга", l_SL)
            
            if shortPos == True and last_hedge <= 0:
                #  установка хеджирующей лонговой позиции                
                if short_upl <= self.hedgeSL :              # crossover                                           and sma_trend > 0
                    # запрет снятие лимитных ордеров                                                     
                    short_limit_Flag = 0 ; long_limit_Flag = 0                           # запрет лимитных ордеров
                    if short_id !=0 : CancelOrder = self.cancel_order(short_id)    # снимаем лимитный шорт ордер
                    if long_id !=0 : CancelOrder = self.cancel_order(long_id)    # снимаем лимитный лонг ордер                        

                    if longPos == False :                        
                        res = self.place_hedge_order('buy', 'long', round(s_pos * hedge_mult,self.round_contract))
                        print (res)

                        # запрос цены LposPrice                        
                        long_pos = self.is_long_position() 
                        LposPrice = long_pos[2]                     # цена открытия позиции
                        l_pos = long_pos[4]                         # кол-во контрактов

                        
                        newLTpTriggerPx = (l_pos * LposPrice * (1 + self.fee_open) - s_pos * SposPrice * (1 - self.fee_open)) / (l_pos * (1 - self.fee_close) - s_pos * (1 + self.fee_close) - round(self.Ep * (1+(s_pos + l_pos)/self.qty/100/10),2)) # формула расчета баланса позиций breakeven

                        #newLTpTriggerPx = (L_C_short * s_pos * SposPrice + S_fee - l_pos * LposPrice + L_fee) / (L_C_short * s_pos + (S_fee/SposPrice) - l_pos + (L_fee/LposPrice)) # формула расчета баланса позиций breakeven

                        print ("newLTpTriggerPx", newLTpTriggerPx)
                        print ("last_price",last_price)

                        L_tp = self.place_algo_tp_order('sell', 'long', newLTpTriggerPx, Long_clOrdId)   # устанавливаем TP на лонг   
                        #LSlTriggerPx = SposPrice - SposPrice /100*self.TP_sz               # вычисляем цену SL
                        #L_tp = self.place_algo_tp_sl_order('sell', 'long', newLTpTriggerPx, LSlTriggerPx, Long_clOrdId )  # устанавливаем SL TP на лонг                  
                        print ("TP лонга",L_tp)
                        if L_tp[1] == 51279:
                            print ("закрываем ТР по маркету 51279", l_pos )
                            close_order = self.place_market_order('sell', 'long', l_pos)
                            print ("close TP order", close_order)
                        else:
                            del_algo = self.cancel_algo_order(S_algoOrdId)                          # чистим шорт
                            print ("чистим шорт",del_algo)
                            STpTriggerPx = SposPrice - SposPrice /100*self.TP_sz               # вычисляем цену TP                                                                                     
                            s_SL = self.place_algo_tp_sl_order('buy', 'short', STpTriggerPx, newLTpTriggerPx, Short_clOrdId )  # устанавливаем SL TP на шорт                 
                            print("TP/SL шорта", s_SL)

                # обновление TP в режиме хеджирования
            if shortPos == True and longPos == True:     
                if s_pos > l_pos:      
                    #if S_algoOrdId != 0 : 
                        last_hedge = -1                        
                        
                        LTpTriggerPx = LposPrice + LposPrice /100*self.TP_sz               # вычисляем цену TP                    
                        
                        #newSTpTriggerPx = (S_C_short * s_pos * SposPrice - l_pos * LposPrice) / (S_C_short * s_pos - l_pos) # формула расчета баланса позиций breakeven
                        #AnewSTpTriggerPx = (S_C_short * s_pos * SposPrice + S_fee - l_pos * LposPrice + L_fee) / (S_C_short * s_pos  - l_pos )
                        #AnewSTpTriggerPx = (l_pos * LposPrice * (1 - L_fee) + s_pos * SposPrice * (1 - S_fee)) / (s_pos * (1 - S_fee) + l_pos * (1 - L_fee))
                        newSTpTriggerPx = (l_pos * LposPrice * (1 + self.fee_open) - s_pos * SposPrice * (1 - self.fee_open)) / (l_pos * (1 - self.fee_close) - s_pos * (1 + self.fee_close) - round(self.Ep * (1+(s_pos + l_pos)/self.qty/100/10),2)) # формула расчета баланса позиций breakeven
                        print ("newSTpTriggerPx ",newSTpTriggerPx)
                        

                        # проверка размера шортового TP                        
                        if S_algoTPpx > newSTpTriggerPx + newSTpTriggerPx/100*0.1 or S_algoTPpx == 0: 
                            print ("debug 1")
                            del_algo = self.cancel_algo_order(S_algoOrdId) # чистим шорт
                            print ("обновление высокого TP для шортовой позиции")
                            #print (del_algo)                            
                            print ("newSTpTriggerPx", newSTpTriggerPx)                            
                            S_tp = self.place_algo_tp_order('buy', 'short', newSTpTriggerPx, Short_clOrdId) # устанавливаем TP на шорт
                            #SSlTriggerPx = LposPrice + LposPrice /100*self.TP_sz               # вычисляем цену SL                                                                                     
                            #S_tp = self.place_algo_tp_sl_order('buy', 'short', newSTpTriggerPx, SSlTriggerPx, Short_clOrdId )  # устанавливаем SL TP на шорт                 
                            print ("TP",S_tp)                            
                            if S_tp[1] == 51277:
                                print ("закрываем ТР по маркету 51277", s_pos )
                                close_order = self.place_market_order('buy', 'short', s_pos)
                                print ("close TP order", close_order)
                            del_algo = self.cancel_algo_order(L_algoOrdId) # чистим лонг
                            print ("чистим лонг",del_algo)
                            l_SL = self.place_algo_tp_sl_order('sell', 'long', LTpTriggerPx, newSTpTriggerPx, Long_clOrdId)  # устанавливаем SL TP на лонг
                            print("установка нового большого SL и маленького TP на лонг",l_SL)

                        # удаление высокого TP для лонговой позиции
                        #if L_algoTPpx > LTpTriggerPx: 
                        #    del_algo = self.cancel_algo_order(L_algoOrdId)
                        #    print ("удаление высокого TP для лонговой позиции")

                if l_pos > s_pos:             
                    #print ("last_hedge",last_hedge)   
                    #if L_algoOrdId != 0 : 
                        last_hedge = 1                               
                        
                        STpTriggerPx = SposPrice - SposPrice /100*self.TP_sz               # вычисляем цену TP                      

                        #newLTpTriggerPx = (L_C_short * s_pos * SposPrice - l_pos * LposPrice) / (L_C_short * s_pos - l_pos) # формула расчета баланса позиций breakeven                                            
                        
                        newLTpTriggerPx = (l_pos * LposPrice * (1 + self.fee_open) - s_pos * SposPrice * (1 - self.fee_open)) / (l_pos * (1 - self.fee_close) - s_pos * (1 + self.fee_close) - round(self.Ep * (1+(s_pos + l_pos)/self.qty/100/10),2)) # формула расчета баланса позиций breakeven
                        
                        # проверка размера лонгового TP                        
                        if L_algoTPpx < newLTpTriggerPx - newLTpTriggerPx/100*0.1:
                            del_algo = self.cancel_algo_order(L_algoOrdId)                          # чистим лонг
                            print ("обновление высокого TP для лонговой позиции")
                            print (del_algo)                            
                            print ("newLTpTriggerPx", newLTpTriggerPx)
                            L_tp = self.place_algo_tp_order('sell', 'long', newLTpTriggerPx, Long_clOrdId)   # устанавливаем TP на лонг                 
                            #LSlTriggerPx = SposPrice - SposPrice /100*self.TP_sz               # вычисляем цену SL                                                                                     
                            #L_tp = self.place_algo_tp_sl_order('sell', 'long', newLTpTriggerPx, LSlTriggerPx, Long_clOrdId )  # устанавливаем SL TP на лонг                 
                            print ("TP",L_tp)
                            if L_tp[1] == 51279:
                                print ("закрываем ТР по маркету 51279", l_pos )
                                close_order = self.place_market_order('sell', 'long', l_pos)
                                print ("close TP order", close_order)
                            del_algo = self.cancel_algo_order(S_algoOrdId)                          # чистим шорт
                            print ("чистим шорт",del_algo)
                            s_SL = self.place_algo_tp_sl_order('buy', 'short', STpTriggerPx, newLTpTriggerPx, Short_clOrdId )  # устанавливаем SL TP на шорт
                            print("установка нового большого SL и маленького TP на шорт", s_SL)
                        # удаление высокого TP для шортовой позиции
                        #if S_algoTPpx > STpTriggerPx: 
                        #    del_algo = self.cancel_algo_order(S_algoOrdId)
                        #    print ("удаление высокого TP для шортовой позиции", del_algo)  
                        

                # закрытие режима хеджирования
            
            if shortPos == True and longPos == False and last_hedge < 0:            # если остался шорт и последний хедж был шортовый, то есть закрылся лонг по своему ТР
                del_algo = self.cancel_algo_order(S_algoOrdId)                      # то удаляем большой ТР шортового хеджа и он становится обычной позицией
                last_hedge = 0

            
            if shortPos == False and longPos == True and last_hedge > 0:            # если остался лонг и последний хедж был лонговый, то есть закрылся шорт по своему ТР
                del_algo = self.cancel_algo_order(L_algoOrdId)                      # то удаляем большой ТР лонгового хеджа и он становится обычной позицией
                last_hedge = 0
            

            if longPos == False and shortPos == False : last_hedge = 0              # если закрыты все позиции, то обнуляем состояние хеджа
            
             # SHORT TP             
            
            shortPos = short_pos[0]          # обновляем данные о наличии позиций    
            longPos = long_pos [0] 
            if shortPos == True and longPos == False and last_hedge >= 0 :   # если Шорт позиция найдена       
                    short_limit_Flag = 0 ; long_limit_Flag = 0                        # запрет лимитных ордеров                           
                    # установка TP
                    STpTriggerPx = SposPrice - SposPrice /100*self.TP_sz               # вычисляем цену TP                                                         
                    if S_algoOrdId == 0 : 
                        print ("устанавливаем ТР на шорт позицию")
                        S_tp = self.place_algo_tp_order('buy', 'short', STpTriggerPx, Short_clOrdId )
                        print("new_tp",S_tp)
                        if S_tp[1] == 51277:
                             print ("закрываем ТР по маркету 51277", s_pos )
                             close_order = self.place_market_order('buy', 'short', s_pos)
                             print ("close TP order", close_order)
                             

                # LONG  TP                              
            if longPos == True and shortPos == False and last_hedge <= 0 :   # если лонг позиция найдена                    
                    short_limit_Flag = 0 ; long_limit_Flag = 0                           # запрет лимитных ордеров                         
                    # установка TP
                    LTpTriggerPx = LposPrice + LposPrice /100*self.TP_sz               # вычисляем цену TP                                        
                    if L_algoOrdId == 0 : 
                        print ("устанавливаем ТР на лонг позицию")
                        L_tp = self.place_algo_tp_order('sell', 'long', LTpTriggerPx, Long_clOrdId) 
                        print("new_tp",L_tp)                       
                        if L_tp[1] == 51279:
                             print ("закрываем ТР по маркету 51279", l_pos )
                             close_order = self.place_market_order('sell', 'long', l_pos)
                             print ("close TP order", close_order)                             

            
                # ЛИМИТНЫЕ ОРДЕРА                       

            # снятие запрета лимитных ордеров   
            if longPos == False and shortPos == False and self.stop_flag == 0: short_limit_Flag = 1 ; long_limit_Flag = 1
            # установка запретов по флагу из конфига
            if self.stop_flag == 1: short_limit_Flag = 0 ; long_limit_Flag = 0

            # запрет ордеров если волатильность меньше пороговой
            if last_volatility < self.min_volatility and short_limit_Flag == 1 and long_limit_Flag == 1:
                print("last_volatility",last_volatility," < " ,self.min_volatility, " , stop limit order")
                short_limit_Flag = 0 ; long_limit_Flag = 0

            # расчет цен ордеров    
            ShortOrderPrice = last_price + last_price/100*self.limit_sz # расчет цены шорт ордера
            #print (ShortOrderPrice)
            LongOrderPrice = last_price - last_price/100*self.limit_sz  # расчет цены лонг ордера
                # вводим правило что лимитка не может быть ниже slow цены
            log = 1    # разговорчивость
            if ShortOrderPrice < slow[-1] + last_price/100*self.limit_sz : ShortOrderPrice = slow[-1] + last_price/100*self.limit_sz           
            if LongOrderPrice > slow[-1] - last_price/100*self.limit_sz: LongOrderPrice = slow[-1] - last_price/100*self.limit_sz            

            # установка лимитных одеров
            if short_id == 0 and short_limit_Flag == 1 :                      
                    if log > 0: print("размещаем лимитный шорт ордер")
                    #print ("ShortOrderPrice",'{:10.11f}'.format (ShortOrderPrice))
                    r = self.place_order('sell','short', self.qty, '{:10.11f}'.format (ShortOrderPrice), Short_clOrdId )
                    #print (r)            

            if long_id == 0 and long_limit_Flag == 1:
                    if log > 0: print("размещаем лимитный лонг ордер")
                    #print ("LongOrderPrice",'{:10.11f}'.format (LongOrderPrice))
                    r = self.place_order('buy','long', self.qty, '{:10.11f}'.format (LongOrderPrice), Long_clOrdId )
                    #print (r)                   

            # снятие лимитных ордеров если есть запреты                                                    
            if short_id !=0 and short_limit_Flag == 0: 
                        CancelOrder = self.cancel_order(short_id)    # снимаем лимитный шорт ордер
                        if log > 0: print ("снимаем лимитный шорт ордер", short_id, "\n", CancelOrder)                        
            if long_id !=0 and long_limit_Flag == 0:
                        CancelOrder = self.cancel_order(long_id)    # снимаем лимитный лонг ордер
                        if log > 0: print ("снимаем лимитный лонг ордер", long_id, "\n", CancelOrder)
                        

           # переставляем лимитки за ценой
            if short_id !=0 and ShortOrderPrice != OldShortOrderPrice and short_limit_Flag == 1:      
                    if log > 0: print("обновляем цену шорт ордера", short_id, "до", '{:10.11f}'.format (ShortOrderPrice))                    
                    CancelOrder = self.cancel_order(short_id)                                        # снимаем лимитный шорт ордер                    
                    r = self.place_order('sell','short', self.qty, '{:10.11f}'.format (ShortOrderPrice), Short_clOrdId )
                    if log > 0: print (r)                
                    OldShortOrderPrice = ShortOrderPrice
            
            if long_id !=0 and LongOrderPrice != OldLongOrderPrice and long_limit_Flag == 1: 
                    if log > 0: print ("обновляем цену лонг ордера",long_id, "до", '{:10.11f}'.format (LongOrderPrice))                                        
                    CancelOrder = self.cancel_order(long_id)                                         # снимаем лимитный лонг ордер                                        
                    r = self.place_order('buy','long', self.qty, '{:10.11f}'.format (LongOrderPrice), Long_clOrdId )
                    if log > 0: print (r)                                    
                    OldLongOrderPrice = LongOrderPrice
            
    
        except Exception as e:
            logger.error(str(e))  
    
            #''''''
        


    def loop(self):
        """
        Цикл проверки.
        Лучше таки это делать опрос не в цикле, а использовать Websocket
        :return:
        """
        a = 0

        while True:    
            start_time = time.time()
            self.check()
            
            a = a + 1
            global last_volatility
            if a == 1 : 
                last_volatility = self.volatility()
                print ("last_volatility ",last_volatility)
                #print (load_dotenv(dotenv_path=".env",override=True)) # перечитывание переменных окружения
                
            if a == 2 : a = 0


            sleep(self.timeout)                
            end_time = time.time()
            elapsed_time = end_time - start_time
            #print(f"время выполнения цикла {elapsed_time:.2f} сек.")

    def run(self):
        """
        Инициализация бота
        :return:
        """
        logger.info("The Bot is started!")
        #self.check_permissions()

        # Можно запускать вечный цикл, если бот локально
        self.loop()
        # Или дергать по крону на ВДСке, по триггеру в Cloud Functions ...
        #self.check()

