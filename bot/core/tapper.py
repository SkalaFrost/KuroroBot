import asyncio
import json
import random
from time import time
from urllib.parse import unquote, quote

import aiohttp
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions import account
from pyrogram.raw.functions.messages import RequestAppWebView
from pyrogram.raw.types import InputBotAppShortName
from .agents import generate_random_user_agent
from bot.config import settings
from typing import Any, Callable
import functools
from bot.utils import logger
from bot.exceptions import InvalidSession
from .headers import headers
from pyrogram.raw.types import InputBotAppShortName, InputNotifyPeer, InputPeerNotifySettings

def error_handler(func: Callable):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in function '{func.__name__}': {e}")
            await asyncio.sleep(1)
    return wrapper

class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.user_id = 0
        self.username = None
        self.first_name = None
        self.last_name = None
        self.fullname = None
        self.start_param = None
        self.peer = None
        self.first_run = None

        self.session_ug_dict = self.load_user_agents() or []

        headers['User-Agent'] = self.check_user_agent()

    async def generate_random_user_agent(self):
        return generate_random_user_agent(device_type='android', browser_type='chrome')

    def info(self, message):
        from bot.utils import info
        info(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def debug(self, message):
        from bot.utils import debug
        debug(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def warning(self, message):
        from bot.utils import warning
        warning(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def error(self, message):
        from bot.utils import error
        error(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def critical(self, message):
        from bot.utils import critical
        critical(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def success(self, message):
        from bot.utils import success
        success(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def save_user_agent(self):
        user_agents_file_name = "user_agents.json"

        if not any(session['session_name'] == self.session_name for session in self.session_ug_dict):
            user_agent_str = generate_random_user_agent()

            self.session_ug_dict.append({
                'session_name': self.session_name,
                'user_agent': user_agent_str})

            with open(user_agents_file_name, 'w') as user_agents:
                json.dump(self.session_ug_dict, user_agents, indent=4)

            logger.success(f"<light-yellow>{self.session_name}</light-yellow> | User agent saved successfully")

            return user_agent_str

    def load_user_agents(self):
        user_agents_file_name = "user_agents.json"

        try:
            with open(user_agents_file_name, 'r') as user_agents:
                session_data = json.load(user_agents)
                if isinstance(session_data, list):
                    return session_data

        except FileNotFoundError:
            logger.warning("User agents file not found, creating...")

        except json.JSONDecodeError:
            logger.warning("User agents file is empty or corrupted.")

        return []

    def check_user_agent(self):
        load = next(
            (session['user_agent'] for session in self.session_ug_dict if session['session_name'] == self.session_name),
            None)

        if load is None:
            return self.save_user_agent()

        return load

    async def get_tg_web_data(self, proxy: str | None) -> str:
        
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            if not self.tg_client.is_connected:
                try:
                    await self.tg_client.connect()

                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)
            
            while True:
                try:
                    peer = await self.tg_client.resolve_peer('KuroroRanchBot')
                    break
                except FloodWait as fl:
                    fls = fl.value

                    logger.warning(f"{self.session_name} | FloodWait {fl}")
                    logger.info(f"{self.session_name} | Sleep {fls}s")
                    await asyncio.sleep(fls + 3)
            
            ref_id = settings.REF_ID if random.randint(0, 100) <= 85 and settings.REF_ID != '' else "ref-C6E90E2D"
            
            web_view = await self.tg_client.invoke(RequestAppWebView(
                peer=peer,
                app=InputBotAppShortName(bot_id=peer, short_name="ranch"),
                platform='android',
                write_allowed=True,
                start_param=ref_id
            ))

            auth_url = web_view.url
            tg_web_data = unquote(string=auth_url.split('tgWebAppData=')[1].split('&tgWebAppVersion')[0])

            me = await self.tg_client.get_me()
            self.user_id = me.id

            if self.tg_client.is_connected:
                await self.tg_client.disconnect()

            return tg_web_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error: {error}")
            await asyncio.sleep(delay=3)
        
        
    async def join_and_mute_tg_channel(self, link: str):
        link = link.replace('https://t.me/', "")
        if not self.tg_client.is_connected:
            try:
                await self.tg_client.connect()
            except Exception as error:
                logger.error(f"{self.session_name} | (Task) Connect failed: {error}")
        try:
            chat = await self.tg_client.get_chat(link)
            chat_username = chat.username if chat.username else link
            chat_id = chat.id
            try:
                await self.tg_client.get_chat_member(chat_username, "me")
            except Exception as error:
                if error.ID == 'USER_NOT_PARTICIPANT':
                    await asyncio.sleep(delay=3)
                    response = await self.tg_client.join_chat(link)
                    logger.info(f"{self.session_name} | Joined to channel: <y>{response.username}</y>")
                    
                    try:
                        peer = await self.tg_client.resolve_peer(chat_id)
                        await self.tg_client.invoke(account.UpdateNotifySettings(
                            peer=InputNotifyPeer(peer=peer),
                            settings=InputPeerNotifySettings(mute_until=2147483647)
                        ))
                        logger.info(f"{self.session_name} | Successfully muted chat <y>{chat_username}</y>")
                    except Exception as e:
                        logger.info(f"{self.session_name} | (Task) Failed to mute chat <y>{chat_username}</y>: {str(e)}")
                    
                    
                else:
                    logger.error(f"{self.session_name} | (Task) Error while checking TG group: <y>{chat_username}</y>")

            if self.tg_client.is_connected:
                await self.tg_client.disconnect()
        except Exception as error:
            logger.error(f"{self.session_name} | (Task) Error while join tg channel: {error}")

    @error_handler
    async def make_request(self, http_client, method, endpoint=None, url=None, **kwargs):
        full_url = url or f"https://ranch-api.kuroro.com/api{endpoint or ''}"
        response = await http_client.request(method, full_url, **kwargs)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return await response.json()
        else:
            return await response.text()
        
    @error_handler
    async def get_user(self, http_client):
       return await self.make_request(http_client, 'GET', endpoint="/Game/GetPlayerState")
    
    @error_handler
    async def get_onboard(self, http_client):
       return await self.make_request(http_client, 'GET', endpoint="/Onboarding/GetOnboardingState")
    
    @error_handler
    async def update_coins(self, http_client):
       return await self.make_request(http_client, 'POST', endpoint="/Game/UpdateCoinsSnapshot")
    
    @error_handler
    async def get_coinsearnedaway(self, http_client):
       return await self.make_request(http_client, 'GET', endpoint="/Game/CoinsEarnedAway")
    
    @error_handler
    async def get_listings(self, http_client):
       return await self.make_request(http_client, 'GET', endpoint="/CoinsShop/GetListings")
    
    @error_handler
    async def buy_item(self, http_client,itemId):
       data = {"itemId":itemId}
       return await self.make_request(http_client, 'POST', endpoint="/CoinsShop/BuyItem",json = data)
    
    @error_handler
    async def get_daily_streak_state(self, http_client):
       return await self.make_request(http_client, 'GET', endpoint="/DailyStreak/GetState")
    
    @error_handler
    async def claim_daily_bonus(self, http_client):
        return await self.make_request(http_client, 'POST', endpoint="/DailyStreak/ClaimDailyBonus", json = {})
    
    @error_handler
    async def perform_farming(self, http_client,mine_amount):
        await self.save(http_client=http_client,x=[100,200],y=[228,385],n = random.randint(int(mine_amount)-5,int(mine_amount)))
        data = {
                "mineAmount": mine_amount,
                "feedAmount": 0
            }
        return await self.make_request(http_client, 'POST', endpoint="/Clicks/MiningAndFeeding", json = data)

    @error_handler
    async def perform_feeding(self, http_client,feed_amount):
        await self.save(http_client=http_client,x=[3,85],y=[200,357],n = random.randint(int(feed_amount)-5,int(feed_amount)))
        data = {
                "mineAmount": 0,
                "feedAmount": feed_amount
            }
        return await self.make_request(http_client, 'POST', endpoint="/Clicks/MiningAndFeeding", json = data)
    
    @error_handler
    async def get_purchasable_upgrades(self, http_client):
        return await self.make_request(http_client, 'GET', endpoint="/Upgrades/GetPurchasableUpgrades")

    @error_handler
    async def buy_upgrade(self, http_client,upgrade_id):
        data = {"upgradeId": upgrade_id}
        return await self.make_request(http_client, 'POST', endpoint="/Upgrades/BuyUpgrade", json = data)

    @error_handler
    async def get_quest(self, http_client):
        return await self.make_request(http_client, 'GET', endpoint="/Quests/GetActiveQuests")
    
    @error_handler
    async def get_inventory(self, http_client):
        return await self.make_request(http_client, 'GET', endpoint="/Inventory/GetInventory")
    
    @error_handler
    async def get_raffle_tickets(self, http_client):
        return await self.make_request(http_client, 'GET', endpoint="/RaffleTickets/GetRaffleTickets")
    
    @error_handler
    async def get_ball_state(self, http_client):
        return await self.make_request(http_client, 'GET', endpoint="/EnergyBalls/GetEnergyBallState")
    
    @error_handler
    async def use_item(self, http_client,itemId):
        data = {"itemId":itemId}
        return await self.make_request(http_client, 'POST', endpoint="/Inventory/UseItem",json = data)
    
    @error_handler
    async def use_raffle(self, http_client):
        data = {}
        return await self.make_request(http_client, 'POST', endpoint="/RaffleTickets/UseRaffleTicket",json = data)
    
    @error_handler
    async def hit_ball(self, http_client,user_id,hits):
        await self.save(http_client=http_client,x=[50,300],y=[50,300],n = random.randint(int(hits) - 5,int(hits)))
        data = {"hits":hits}
        return await self.make_request(http_client, 'POST', endpoint=f"/EnergyBalls/TakeHitsCombo/tg-{user_id}:main",json = data)
    
    @error_handler
    async def save(self, http_client,x:list, y:list, n=1):
        data = [{"x":random.randint(*x),"y":random.randint(*y)}]*n
        return await self.make_request(http_client, 'POST', endpoint=f"/Bf/Save",json = data)
    
    @error_handler
    async def reincarnate(self, http_client):
        data = {}
        return await self.make_request(http_client, 'POST', endpoint=f"/Reincarnate/Reincarnate",json = data)

    @error_handler
    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        response = await self.make_request(http_client, 'GET', url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
        ip = response.get('origin')
        logger.info(f"{self.session_name} | Proxy IP: {ip}")

    @error_handler
    async def welcome(self, http_client):
        
        step_1 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"PreStarterSelection"})
        await asyncio.sleep(1,3)
        
        if step_1 == "":
            step_2 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"StarterSelection"})
        await asyncio.sleep(1,3)  
        
        if step_2 == "":
            step_3 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/SelectStarter"
                                       ,json = {"starterOption": "Digby"})
        await asyncio.sleep(1,3)

        if step_3 == "":
            step_4 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep": "TappingEgg"})
        await asyncio.sleep(1,3)  

        if step_4 == "":
            step_5 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"BeastHatched"})
        await asyncio.sleep(1,3)  

        if step_5 == "":
            step_6 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"HelloBeast"})
        await asyncio.sleep(1,3)  

        if step_6 == "":
            step_7 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"FeedBeast"})
        await asyncio.sleep(1,3)  

        if step_7 == "":
            step_8 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"MoodXpExplanation"})
        await asyncio.sleep(1,3)  

        if step_8 == "":
            step_9 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"PreMineShards"})
        await asyncio.sleep(1,3)  

        if step_9 == "":
            step_10 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"MineShards"})
        await asyncio.sleep(1,3)  

        if step_10 == "":
            step_11 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"FeedBeastAgain"})
        await asyncio.sleep(1,3)  

        if step_11 == "":
            step_12 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"FeedBeastMore"})
        await asyncio.sleep(1,3)  

        if step_12 == "":
            step_13 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"BeastLevelUp"})
        await asyncio.sleep(1,3)  

        if step_13 == "":
            step_14 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"CoinSpendingUpgrades"})
        await asyncio.sleep(1,3)  

        if step_14 == "":
            step_15 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"CoinEarningAway"})
        await asyncio.sleep(1,3)  

        if step_15 == "":
            step_16 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"MoreLevelMoreCoins"})
        await asyncio.sleep(1,3)  

        if step_16 == "":
            step_17 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"BeastHappinessAway"})
        await asyncio.sleep(1,3) 

        if step_17 == "":
            step_18 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"BeastHappinessAway2"})
        await asyncio.sleep(1,3) 

        if step_18 == "":
            step_19 = await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/UpdateStep"
                                       ,json = {"newStep":"ThatsAll"})
        await asyncio.sleep(1,3) 

        if step_19 == "":
            step_20 =  await self.make_request(http_client, 'POST', endpoint=f"/Onboarding/CompleteOnboarding"
                                       ,json = {})

        if step_20 == "":
            return True
        else: return False

    async def run(self, proxy: str | None) -> None:
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None

        http_client = CloudflareScraper(headers=headers, connector=proxy_conn)

        if proxy:
            await self.check_proxy(http_client=http_client, proxy=proxy)
        init_data = None
        init_data_live_time = random.randint(3300, 3600)
        init_data_created_time = 0
        while True:
            try: 
                if time() - init_data_created_time >= init_data_live_time or init_data is None:
                    init_data = await self.get_tg_web_data(proxy=proxy)
                    init_data_created_time = time()
                    http_client.headers['authorization'] = f'Bearer {init_data}'

                onboard_res = await self.get_onboard(http_client=http_client)
                if onboard_res and onboard_res.get("currentStep","") == "WelcomeMessage":
                    wellcome_res = await self.welcome(http_client=http_client)
                    if not wellcome_res:
                        self.warning("<light-yellow>Register Failed, Try again</light-yellow> ")
                        
                elif onboard_res and onboard_res.get("currentStep","") == "ThatsAll":
                    user_res = await self.get_user(http_client=http_client)
                    await self.save(http_client=http_client,x = [10,450],y = [10,600])
                    coins_earn_res = await self.get_coinsearnedaway(http_client=http_client)
                    await self.update_coins(http_client=http_client)
                    get_raffle_tickets_res = await self.get_raffle_tickets(http_client)

                    if user_res and coins_earn_res is not None: 
                        balance = user_res.get("coinsSnapshot",{}).get("value",0)
                        shards  = user_res.get("shards",0)
                        beast_lvl = user_res.get("beast",{}).get("level",0)
                        energy = user_res.get("energySnapshot",{}).get("value",0)
                        raffle_tickets = get_raffle_tickets_res.get("count",0)
                        self.info(f"Earn <cyan>{coins_earn_res}</cyan> coins - "
                                f"Balance: <cyan>{balance}</cyan> - "
                                f"Shards: <cyan>{shards}</cyan> - "
                                f"Raffle Tickets: <cyan>{raffle_tickets}</cyan> - "
                                f"Beast lvl: <cyan>{beast_lvl}</cyan>")

                    else: 
                        await asyncio.sleep(300,800)
                        continue

                    if settings.AUTO_REINCARNATE and beast_lvl > settings.REINCARNATE_LVL:
                        reincarnate_res = await self.reincarnate(http_client=http_client)
                        if reincarnate_res is not None:
                            self.info("Reincarnate suceeded")

                    state_response = await self.get_daily_streak_state(http_client = http_client)
                    if not state_response.get('isTodayClaimed',''):

                        claim_response = await self.claim_daily_bonus(http_client=http_client)
                        if claim_response:
                            self.info(f"{claim_response['message']}")
                        else:
                            self.info("Reward already claimed today")
                    else:
                        self.info("You have received the reward today.")

                    for _ in range(raffle_tickets):
                        recv_item = await self.use_raffle(http_client=http_client)
                        if recv_item:
                            self.info(f"Use raffle ticket successfully, get <cyan>{recv_item}</cyan>")

                    ball_state_res = await self.get_ball_state(http_client=http_client)
                    health  = ball_state_res.get('currentHealth',0) + 3

                    if not ball_state_res.get("isDestroyed",True):
                        for _ in range(random.randint(10, 20)):
                            hits = random.randint(5,10)
                            hit_ball_res = await self.hit_ball(http_client=http_client,user_id = self.user_id, hits = hits if hits < health else health)
                            if hit_ball_res is None:
                                break
                            self.info(f"Hitting ball succeeded, number of hits: <cyan>{hits}</cyan>")
                            await asyncio.sleep(random.randint(2,5))

                    while energy > 0:
                        mine_amount = random.randint(*settings.MINE_AMOUNT)
                        farm_response = await self.perform_farming(http_client=http_client,mine_amount = mine_amount if mine_amount < energy else energy)
                        if farm_response is not None: 
                            energy -= mine_amount 
                            self.info(f"Farming succeeded, mined amount: <cyan>{mine_amount}</cyan>")
                        else: 
                            break
                        await asyncio.sleep(random.randint(2,5))

          
                    while shards > 0:
                        feed_amount = random.randint(*settings.FEED_AMOUNT)
                        feed_response = await self.perform_feeding(http_client=http_client,feed_amount = feed_amount if feed_amount < shards else shards)
                        if feed_response is not None: 
                                shards -= feed_amount
                                self.info(f"Feeding succeeded, feeding amount: <cyan>{feed_amount}</cyan>")
                        else: 
                            break
                        await asyncio.sleep(random.randint(2,5))

                    free_money = balance - settings.SAVE_COIN
                    list_items = await self.get_listings(http_client=http_client)
                    instock = [ item for item in list_items if item["inStock"] ]
                    for item in instock:
                        if free_money > item["coinCost"]:
                            buy_items_res = await self.buy_item(http_client=http_client,itemId = item['itemId'])
                            if "successfully" in buy_items_res.get("message",""):
                                self.info(f"Bought <cyan>{item['name']}</cyan> succeeded!")

                    inventory_items = await self.get_inventory(http_client=http_client)
                    message = "Inventory: "
                    dict_items = {}
                    for item in inventory_items:
                        dict_items[item['itemId']] = item['quantity']
                        message += f"{item['itemId'].replace('-',' ').title()}: <cyan>{item['quantity']}</cyan> - "
                    self.info(message.strip(' - '))

                    if dict_items.get("shards",0) >=1:
                        await self.use_item(http_client=http_client,itemId = 'shards')
                    if dict_items.get("energy-drink",0) >=1 and energy <= 0:
                        use_item_res = await self.use_item(http_client=http_client,itemId = 'energy-drink')
                        if use_item_res is not None:
                            self.info("Using Energy Drink")
                            start_time = time()  
                            while time() - start_time < 15:  
                                mine_amount = random.randint(80,100)
                                farm_response = await self.perform_farming(http_client=http_client,mine_amount = mine_amount)

                    if settings.AUTO_UPGRADE:
                        upgrades_response = await self.get_purchasable_upgrades(http_client=http_client)
                        for upgrade in upgrades_response:
                            if upgrade["canBePurchased"] and upgrade["cost"] < free_money:
                                buy_response = await self.buy_upgrade(http_client = http_client, upgrade_id = upgrade["upgradeId"])
                                if buy_response:
                                    free_money -= upgrade["cost"]
                                    self.success(f"Successfully bought <cyan>{upgrade['name']}</cyan> for <cyan>{upgrade['cost']}</cyan> coins, earning <cyan>{upgrade['earnIncrement']}</cyan> per hour")
                                    await asyncio.sleep(random.randint(2,10))
                                else:
                                    self.error(f"Failed to buy upgrade {upgrade['name']}")
             

            except InvalidSession as error:
                raise error

            except Exception as error:
                self.error(f"Unknown error: {error}")
                await asyncio.sleep(delay=3)
            else:
                sleep_time = random.randint(settings.SLEEP_TIME[0], settings.SLEEP_TIME[1])
                self.info(f"Sleep <y>{sleep_time}s</y>")
                await asyncio.sleep(delay=sleep_time)    
            

async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
