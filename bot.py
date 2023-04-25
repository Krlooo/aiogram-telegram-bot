import asyncio
import logging
import json
import sqlite3
from typing import Any, Dict
import cloudinary
from cloudinary import CloudinaryImage
from cloudinary.uploader import upload
from cloudinary.utils import cloudinary_url
import uuid
import re
import os
from dotenv import load_dotenv
import feedparser
import aiogram
from aiogram import Router
from aiogram import Bot, Dispatcher, F, Router, html, utils
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.utils import keyboard
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.callback_data import CallbackData, CallbackQuery
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,

)
import more_itertools
load_dotenv()
# Variables
BOT_API_KEY = os.getenv('BOT_API_KEY')
RSS_FEED_URL = os.getenv('RSS_FEED_URL')
DB_NAME = os.getenv('DB_NAME')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')
# Cloudinary Config
# cloudinary.config(
#     cloud_name="detsv0rmo",
#     api_key=CLOUDINARY_API_KEY,
#     api_secret=CLOUDINARY_API_SECRET,
#     secure=True
# )


# Bot token
TOKEN = BOT_API_KEY

# RSS feed URL
FEED_URL = RSS_FEED_URL


# All handlers should be attached to the Router (or Dispatcher)
router = Router()

# Function to connect to the db and create table if not exist


class Form(StatesGroup):
    addword = State()
    delword = State()


class MyCallback(CallbackData, prefix="my"):
    fun: str
    msg: str
# Function to connect to the db and create table if not exist


def connect_database(database_name):
    # Conectar con la base de datos o crearla si no existe
    conn = sqlite3.connect(database_name)

    # Crear una tabla si no existe
    conn.execute('''CREATE TABLE IF NOT EXISTS words
                (id INTEGER,
                word TEXT NOT NULL);''')

    # Devolver la conexión
    return conn

# Function to insert a word into a table


def insert_word(word, id):
    conn = connect_database(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO words (id, word) VALUES (?, ?)",
              (id, word.casefold()))
    conn.commit()
    c.close()
    conn.close()


async def delete_word(word, id):
    conn = connect_database(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM words WHERE (id, word) = (?, ?)",
              (id, word.casefold()))
    conn.commit()
    c.close()
    conn.close()
# function to check if a word is already inserted


def check_word(word, id):
    conn = connect_database(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM words WHERE word = ? AND id = ?",
              (word.casefold(), id))
    result = c.fetchone()
    c.close()
    conn.close()
    return result is not None

# Function to check if a word is in the database and returns id


def check_word_on_item(word):
    conn = connect_database(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id FROM words WHERE word LIKE ?",
              [word.casefold() + '%'])
    results = c.fetchall()
    c.close()
    conn.close()
    id_list = [row[0] for row in results if row[0] is not None]
    return id_list


# Function that starts the add command


@router.message(Command("del"))
async def command_start(message: Message, state: FSMContext) -> None:
    word_list = await recover_word_list(message.chat.id)
    builder = InlineKeyboardBuilder()
    for entry in word_list:
        builder.button(text=f"{entry}", callback_data=MyCallback(
            fun="del_word", msg=entry).pack())
    builder.adjust(3, 2)
    await state.set_state(Form.delword)
    await message.answer("¿Que palabra quieres borrar?\nPuedes escribirla, o, en unos segundos te mostraré tu lista de palabras, y pulsado encima de ellas podras borrarla.", reply_markup=builder.as_markup())
    # await bot.edit_message_text(text="¿Que palabra quieres borrar?\nPuedes escribirla, o, en unos segundos te mostraré tu lista de palabras, y pulsado encima de ellas podras borrarla.",
    #                             chat_id=message.chat.id, message_id=last_message.message_id, reply_markup=ReplyKeyboardMarkup(
    #                                 keyboard=[
    #                                     [
    #                                         KeyboardButton(
    #                                             text="Cancelar")
    #                                     ]
    #                                 ],
    #                                 resize_keyboard=True,
    #                             ))


@router.callback_query(MyCallback.filter(F.fun == "del_word"))
async def my_callback_foo(query: CallbackQuery, callback_data: MyCallback):
    await delete_word(callback_data.msg.casefold(), query.message.chat.id)
    builder = InlineKeyboardBuilder()
    word_list = await recover_word_list(query.message.chat.id)
    for entry in word_list:
        builder.button(text=f"{entry}", callback_data=MyCallback(
            fun="del_word", msg=entry).pack())
    builder.adjust(3, 2)
    await bot.edit_message_text(f'Acabo de eliminar <b>{callback_data.msg}</b>\n¿Que palabra quieres borrar ahora?',
                                query.from_user.id,
                                query.message.message_id, reply_markup=builder.as_markup())


@ router.message(Command("add"))
async def command_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Form.addword)
    await message.answer(
        "¿Que palabra quieres añadir?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text="Cancelar")
                ]
            ],
            resize_keyboard=True,
        ),
    )
# Function to wait the word "cancelar" from user to cancel the current add operation


@ router.message(F.text.casefold() == "cancelar")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    """
    Allow user to cancel any action
    """
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer(
        "Cancelado.",
        reply_markup=ReplyKeyboardRemove(),
    )

# Function to add word command


async def recover_word_list(user_id):
    conn = connect_database(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT word FROM words WHERE id = ?", [(user_id)])
    results = c.fetchall()
    c.close()
    conn.close()
    result = [item for sublist in results for item in sublist]
    return result


@router.message(Form.delword)
async def del_word(message: Message, state: FSMContext) -> None:
    if not message.text.casefold().isalnum():
        await message.answer(
            f"La palabra {html.quote(message.text)}, contiene caracteres ilegales, prueba con otra.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [
                        KeyboardButton(text="Cancelar")
                    ]
                ],
                resize_keyboard=True,
            ),
        )
    elif check_word(message.text.casefold(), message.chat.id):
        delete_word(message.text.casefold(), message.chat.id)
        await message.answer(
            f"La palabra {html.quote(message.text)}, se ha borrado correctamente!",
            reply_markup=ReplyKeyboardRemove())
        await state.clear()
        # Llamar a otra función aquí si la inserción fue exitosa
    else:
        await message.answer(
            f"La palabra: {html.quote(message.text)}, no existe, prueba con otra!",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [
                        KeyboardButton(text="Cancelar")
                    ]
                ],
                resize_keyboard=True,
            ),
        )


@router.message(Form.addword)
async def add_word(message: Message, state: FSMContext) -> None:

    if not message.text.casefold().isalnum():
        await message.answer(
            f"La palabra {html.quote(message.text)}, contiene caracteres ilegales, prueba con otra.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [
                        KeyboardButton(text="Cancelar")
                    ]
                ],
                resize_keyboard=True,
            ),
        )
        # Llamar a otra función aquí si la inserción fue exitosa
    elif check_word(message.text.casefold(), message.chat.id):
        await message.answer(
            f"La palabra {html.quote(message.text)}, ya existe, prueba a decirme otra!",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [
                        KeyboardButton(text="Cancelar")
                    ]
                ],
                resize_keyboard=True,
            ),
        )

    else:
        insert_word(message.text.casefold(), message.chat.id)
        await state.update_data(name=message.text)
        await state.clear()
        await message.answer(
            f"He añadido la palabra: {html.quote(message.text)}!",
            reply_markup=ReplyKeyboardRemove())


def load_last_titles():
    try:
        with open('last_titles.json', 'r') as f:
            last_titles = set(json.load(f))
    except:
        with open('last_titles.json', 'w') as f:
            json.dump([], f)
            last_titles = set()
    return last_titles


def save_last_titles(last_titles):
    with open('last_titles.json', 'w') as f:
        json.dump(list(last_titles), f)


# def custom_image(imgs, id):
#     upload(imgs, public_id=id)
#     img = CloudinaryImage("jfvk7eavulevdnt3bvss.jpg").image(transformation=[
#         {'overlay': id},
#         {'flags': "relative", 'width': "260", "height": "300",
#             'crop': "scale", 'gravity': "center", 'y': 18, 'x': -20},
#         {'flags': "layer_apply", "y": "90"}
#     ])
#     last = re.search('"(.*?)"', img).group(1)
#     return last


async def dm_alerts(item_title, deal_id, message: Message) -> None:
    words = item_title.split()
    inlines_keyboard_dm = [[InlineKeyboardButton(
        text="Ir al chollo!🔥", url=f"https://t.me/OfertasYcupones/{deal_id}")]]
    for word in words:
        fresh_word = re.sub(r'[^a-zA-Z]', '', word)
        if len(fresh_word) > 3:
            ids = check_word_on_item(fresh_word.casefold())
            if ids:
                for id in ids:
                    try:
                        await message.send_message(chat_id=id, text=f'''🔥🔥🔥🔥\nHe encontrado un chollo con la palabra {word}
                                \n🔥🔥🔥🔥
                                \n<b>Este es su título:</b>
                                \n{item_title}''',
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=inlines_keyboard_dm))
                    except:
                        None

@router.message()
async def handle_new_items(message: Message) -> None:

    # Cargamos el json con los valores de last_titles
    last_titles = load_last_titles()
    # Get the new items from the RSS feed
    feed = feedparser.parse(FEED_URL)
    new_items = [
        item for item in feed.entries if item.title and item.link not in last_titles]

    # If there are new items, send a message for each one
    if new_items:
        for items in new_items:
            item_price, item_url, item_title, item_img = items.get("pepper_merchant", {}).get(
                "price", "Ver en la web!"), items.link, items.title, items.media_content[0]["url"].replace(
                "/re/150x150/", "/")
            # imagen que conecta con cloudinary para añadir fondo personalizado y letras
            # item_img = custom_image(item_img,  str(uuid.uuid4()))
            inlines_keyboard = [[InlineKeyboardButton(text=item_price+"💱", url=item_url),
                                 InlineKeyboardButton(text="¡Charla!🔥", url="https://t.me/OfertasMXChat")]]

            id_for_dm = await message.send_message(chat_id="@OfertasYcupones", text=f"<a href='{item_img}'>🔥</a>🔥📉#OfertaHot\n\n<b>{item_title}</b>", parse_mode="HTML",
                                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=inlines_keyboard))
            dm_id = id_for_dm.message_id
            await dm_alerts(item_title=item_title, deal_id=dm_id, message=message)
            last_titles.update(item.title and item.link for item in new_items)
        #  Abrimos el json para guardar las ultimas entradas
            save_last_titles(last_titles)


async def main() -> None:
    # Dispatcher is a root router
    dp = Dispatcher()
    # ... and all other routers should be attached to Dispatcher
    dp.include_router(router)

    # Initialize Bot instance with a default parse mode which will be passed to all API calls
    global bot
    bot = Bot(TOKEN, parse_mode="HTML")

    # Check for new items every 5 minutes
    async def check_new_items() -> None:
        while True:
            await handle_new_items(message=bot)
            await asyncio.sleep(60)

    asyncio.create_task(check_new_items())
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        while True:
            logging.basicConfig(level=logging.INFO)
            # Espere un segundo antes de volver a ejecutar la tarea
            asyncio.run(main())
    except KeyboardInterrupt:
        # Maneje la interrupción del teclado de forma segura
        print("Interrupción del teclado detectada. Deteniendo tarea...")
