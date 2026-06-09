from __future__ import annotations

import argparse
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.auth import hash_api_key
from app.config import settings
from app.database import Base, engine
from app.models import AuditAction, Chain, Drink, Shop, User, UserRole
from app.services.menus import (
    add_or_update_menu_item,
    get_or_create_chain_template_menu,
    get_or_create_outlet_menu,
    sync_template_to_outlets,
    unique_slug,
)

CHECKED_ON = "2026-06-08"

SOURCE_NOTES = {
    "yakun": (
        "Price source: DrinkWhisper Ya Kun Menu 2026, checked "
        f"{CHECKED_ON}. Outlet source: Ya Kun Find Us."
    ),
    "toast_box": (
        "Price source: DrinkWhisper Toast Box Menu 2026, checked "
        f"{CHECKED_ON}. Outlet source: Toast Box locations."
    ),
    "luckin": (
        "Price source: SG Restaurant Menu Luckin Coffee Singapore Menu 2025, "
        f"checked {CHECKED_ON}. Outlet source: Syioknya Downtown Core locations."
    ),
    "starbucks": (
        "Price source: MySGMenu Starbucks Singapore Review 2026, checked "
        f"{CHECKED_ON}. Outlet source: public mall/store directory pages."
    ),
    "huggs": (
        "Price source: SGEats Huggs Coffee Menu 2025, checked "
        f"{CHECKED_ON}. Outlet source: official Huggs locations page."
    ),
    "fun_toast": (
        "Price source: SGEats Fun Toast Menu 2025, checked "
        f"{CHECKED_ON}. Outlet source: official Fun Toast outlet pages."
    ),
    "joe_dough": (
        "Price source: SG Restaurants Menu Joe & Dough 2025, checked "
        f"{CHECKED_ON}. Outlet source: official Joe & Dough locations page."
    ),
    "alchemist": (
        "Price source: SGMenu Alchemist menu 2024, checked "
        f"{CHECKED_ON}. Outlet source: official Alchemist visit page."
    ),
    "common_man": (
        "Price source: SGMenuGuru Common Man Coffee Roasters 2025, checked "
        f"{CHECKED_ON}. Outlet source: official Common Man locations page."
    ),
    "coffee_bean": (
        "Price source: PriceListo The Coffee Bean & Tea Leaf Singapore 2026, checked "
        f"{CHECKED_ON}. Outlet source: public Change Alley outlet directory."
    ),
    "coffee_break": (
        "Price source: HawkerPedia and Eatbook Coffee Break writeups, checked "
        f"{CHECKED_ON}. Outlet source: official Coffee Break shop page."
    ),
    "tiong_bahru_bakery": (
        "Price source: Raffles City Tiong Bahru Bakery menu page, checked "
        f"{CHECKED_ON}. Outlet source: official Tiong Bahru Bakery site and Raffles City."
    ),
    "arabica": (
        "Price source: Menupro and MenuPrices Arabica Singapore 2025 pages, checked "
        f"{CHECKED_ON}. Outlet source: official Arabica CapitaSpring page."
    ),
    "kenangan": (
        "Price source: Raffles City Kenangan Coffee menu page, checked "
        f"{CHECKED_ON}. Outlet source: Raffles City."
    ),
    "dalkomm": (
        "Price source: Deliveroo dal.komm Coffee Marina Square menu, checked "
        f"{CHECKED_ON}. Outlet source: official dal.komm Singapore site."
    ),
    "blue_bottle": (
        "Price source: Shout Blue Bottle Raffles City opening menu article, checked "
        f"{CHECKED_ON}. Outlet source: Raffles City."
    ),
    "independent": (
        "Price source: user-maintained local demo observations, restored "
        f"{CHECKED_ON} from the local development database."
    ),
    "food_junction": (
        "Price source: user-maintained local demo observations, restored "
        f"{CHECKED_ON} from the local development database."
    ),
    "prata_alley": (
        "Price source: user-maintained local demo observations, restored "
        f"{CHECKED_ON} from the local development database."
    ),
    "old_tea_hut": (
        "Price source: SgMyFoods Old Tea Hut 2026 price table, checked "
        f"{CHECKED_ON}. Outlet source: official Old Tea Hut store locator."
    ),
    "local_coffee_people": (
        "Item and outlet source: official Local Coffee People site, checked "
        f"{CHECKED_ON}. Prices use local demo benchmarks where public price tables are unavailable."
    ),
}


def seed_database(db: Session) -> bool:
    if db.scalar(select(Shop).limit(1)):
        return False

    admin: User | None = None
    if settings.seed_demo_editors:
        admin = User(
            name="Demo Admin",
            email="admin@example.com",
            role=UserRole.admin,
            api_key_hash=hash_api_key("local-demo-admin-key"),
        )
        editor = User(
            name="Demo Editor",
            email="editor@example.com",
            role=UserRole.editor,
            api_key_hash=hash_api_key("local-demo-editor-key"),
        )
        db.add_all([admin, editor])
        db.flush()

    drink_specs = {
        "kopi": ("Kopi", "Nanyang Coffee", "Hot"),
        "kopi_o": ("Kopi-O", "Nanyang Coffee", "Hot"),
        "kopi_c": ("Kopi-C", "Nanyang Coffee", "Hot"),
        "iced_coffee": ("Iced Coffee", "Nanyang Coffee", "Iced"),
        "iced_coffee_o": ("Iced Coffee O", "Nanyang Coffee", "Iced"),
        "iced_coffee_c": ("Iced Coffee C", "Nanyang Coffee", "Iced"),
        "yuan_yang": ("Yuan Yang", "Coffee Tea", "Hot"),
        "iced_yuan_yang": ("Iced Yuan Yang", "Coffee Tea", "Iced"),
        "kopi_melaka": ("Kopi Melaka", "Specialty Coffee", "Iced"),
        "flat_white": ("Flat White", "Milk Coffee", "Regular"),
        "cappuccino": ("Cappuccino", "Milk Coffee", "Regular"),
        "mocha": ("Mocha", "Chocolate Coffee", "Regular"),
        "americano": ("Americano", "Black Coffee", "Regular"),
        "white_americano": ("White Americano", "Black Coffee", "Regular"),
        "hazelnut_latte": ("Hazelnut Latte", "Milk Coffee", "Regular"),
        "vanilla_latte": ("Vanilla Latte", "Milk Coffee", "Regular"),
        "caramel_latte": ("Caramel Latte", "Milk Coffee", "Regular"),
        "latte_gula": ("Latte Gula", "Specialty Coffee", "Regular"),
        "archipelago_cold_brew": ("Archipelago Cold Brew", "Cold Coffee", "Regular"),
        "iced_kopi_grande": ("Iced Kopi Grande", "Nanyang Coffee", "Grande"),
        "iced_kopi_c_grande": ("Iced Kopi C Grande", "Nanyang Coffee", "Grande"),
        "iced_kopi_o_grande": ("Iced Kopi O Grande", "Nanyang Coffee", "Grande"),
        "fun_coffee": ("Coffee", "Nanyang Coffee", "Large"),
        "fun_coffee_o": ("Coffee O", "Nanyang Coffee", "Large"),
        "fun_coffee_c": ("Coffee C", "Nanyang Coffee", "Large"),
        "gula_melaka_coffee": ("Gula Melaka Coffee", "Specialty Coffee", "Large"),
        "caffe_latte": ("Caffe Latte", "Milk Coffee", "Tall"),
        "iced_caffe_latte": ("Iced Caffe Latte", "Milk Coffee", "Tall"),
        "caffe_americano": ("Caffe Americano", "Black Coffee", "Tall"),
        "caramel_macchiato": ("Caramel Macchiato", "Milk Coffee", "Tall"),
        "white_chocolate_mocha": ("White Chocolate Mocha", "Chocolate Coffee", "Tall"),
        "vanilla_sweet_cream_cold_brew": (
            "Vanilla Sweet Cream Cold Brew",
            "Cold Coffee",
            "Tall",
        ),
        "coconut_latte": ("Coconut Latte", "Milk Coffee", "Regular"),
        "iced_minty_coconut_latte": ("Iced Minty Coconut Latte", "Milk Coffee", "Regular"),
        "creamy_dreamy_latte": ("Creamy Dreamy Latte", "Milk Coffee", "Regular"),
        "toffee_hazelnut_latte": ("Toffee Hazelnut Latte", "Milk Coffee", "Regular"),
        "creme_brule_latte": ("Creme Brule Latte", "Milk Coffee", "Regular"),
        "big_cheese_latte": ("Big Cheese Latte", "Milk Coffee", "Regular"),
        "piccolo_latte": ("Piccolo Latte", "Milk Coffee", "400ml"),
        "dr_joe": ("Signature D.R. Joe", "Milk Coffee", "450ml"),
        "manuka_honey_latte": ("Manuka Honey Latte", "Milk Coffee", "450ml"),
        "avocado_cafe_latte": ("Avocado Cafe Latte", "Specialty Coffee", "450ml"),
        "dirty_matcha": ("Dirty Matcha", "Coffee Tea", "450ml"),
        "espresso": ("Espresso", "Black Coffee", "400ml"),
        "batch_brew": ("Batch Brew", "Filter Coffee", "400ml"),
        "black_coffee": ("Black Coffee", "Black Coffee", "400ml"),
        "white_coffee": ("White Coffee", "Milk Coffee", "400ml"),
        "iced_black": ("Iced Black", "Black Coffee", "450ml"),
        "iced_white": ("Iced White", "Milk Coffee", "450ml"),
        "iced_mocha": ("Iced Mocha", "Chocolate Coffee", "450ml"),
        "iced_americano": ("Iced Americano", "Black Coffee", "450ml"),
        "iced_latte": ("Iced Latte", "Milk Coffee", "450ml"),
        "oat_milk_latte": ("Oat Milk Latte", "Milk Coffee", "450ml"),
        "mocha_latte": ("Mocha Latte", "Chocolate Coffee", "450ml"),
        "salted_caramel_latte": ("Salted Caramel Latte", "Milk Coffee", "450ml"),
        "spanish_latte": ("Spanish Latte", "Milk Coffee", "450ml"),
        "sea_salt_caramel_latte": ("Sea Salt Caramel Latte", "Specialty Coffee", "450ml"),
        "black_sesame_latte": ("Black Sesame Latte", "Specialty Coffee", "450ml"),
        "butter_pecan_latte": ("Butter Pecan Latte", "Specialty Coffee", "450ml"),
        "taro_milk_latte": ("Taro Milk Latte", "Specialty Coffee", "450ml"),
        "macchiato": ("Macchiato", "Milk Coffee", "400ml"),
        "long_black": ("Long Black", "Black Coffee", "400ml"),
        "magic": ("Magic", "Milk Coffee", "400ml"),
        "dark_latte": ("Dark Latte", "Milk Coffee", "450ml"),
        "kyoto_latte": ("Kyoto Latte", "Specialty Coffee", "450ml"),
        "espresso_macchiato": ("Espresso Macchiato", "Milk Coffee", "400ml"),
        "kenangan_latte": ("Kenangan Latte", "Specialty Coffee", "450ml"),
        "creamy_latte": ("Creamy Latte", "Milk Coffee", "450ml"),
        "creamy_aren_latte": ("Creamy Aren Latte", "Specialty Coffee", "450ml"),
        "avocado_coffee": ("Avocado Coffee", "Specialty Coffee", "450ml"),
        "rose_latte": ("Rose Latte", "Specialty Coffee", "450ml"),
        "coffee_cube": ("Coffee Cube", "Cold Coffee", "450ml"),
        "honey_coffee_cube": ("Honey Coffee Cube", "Cold Coffee", "450ml"),
        "gibraltar": ("Gibraltar", "Milk Coffee", "400ml"),
        "drip_coffee": ("Drip Coffee", "Filter Coffee", "400ml"),
        "cold_brew": ("Cold Brew", "Cold Coffee", "450ml"),
        "tea_o": ("Tea O", "Tea", None),
        "teh": ("Teh", "Tea", None),
        "teh_c": ("Teh C", "Tea", None),
        "milo": ("Milo", "Milo", None),
        "iced_milo": ("Iced Milo", "Milo", None),
        "iced_tea_o": ("Iced Tea O", "Tea", None),
        "iced_tea": ("Iced Tea", "Tea", None),
        "iced_teh_c": ("Iced Teh C", "Tea", None),
        "iced_milo_dinosaur": ("Iced Milo Dinosaur", "Milo", None),
        "horlicks": ("Horlicks", "Horlicks", None),
        "iced_horlicks": ("Iced Horlicks", "Horlicks", None),
        "homemade_iced_lemon_tea": ("Homemade Iced Lemon Tea", "Tea", None),
        "homemade_lemon_tea": ("Homemade Lemon Tea", "Tea", None),
        "honey_water": ("Honey Water", "Honey", None),
        "iced_honey_water": ("Iced Honey Water", "Honey", None),
        "barley": ("Barley", "Barley", None),
        "iced_barley": ("Iced Barley", "Barley", None),
        "iced_calamansi_tea": ("Iced Calamansi Tea", "Tea", None),
        "iced_lime_juice_sour_plum": ("Iced Lime Juice with Sour Plum", "Juice", None),
        "teh_tarik": ("Teh Tarik", "Tea", None),
        "kopi_tarik": ("Kopi Tarik", "Nanyang Coffee", None),
        "honey_lemon": ("Honey Lemon", "Honey", None),
        "iced_honey_lemon": ("Iced Honey Lemon", "Honey", None),
        "yuan_yang_o": ("Yuan Yang O", "Coffee Tea", "400ml"),
        "yuan_yang_c": ("Yuan Yang C", "Coffee Tea", "400ml"),
        "honey_coffee_o": ("Honey Coffee O", "Specialty Coffee", "400ml"),
        "honey_milk_coffee": ("Honey Milk Coffee", "Specialty Coffee", "400ml"),
        "almond_coffee_o": ("Almond Coffee O", "Specialty Coffee", "400ml"),
        "almond_milk_coffee": ("Almond Milk Coffee", "Specialty Coffee", "400ml"),
        "almond_milk_coffee_c": ("Almond Milk Coffee C", "Specialty Coffee", "400ml"),
        "gula_melaka_milk_coffee": ("Gula Melaka Milk Coffee", "Specialty Coffee", "450ml"),
        "gula_melaka_milk_coffee_c": ("Gula Melaka Milk Coffee C", "Specialty Coffee", "450ml"),
        "lemon_tea": ("Lemon Tea", "Tea", "400ml"),
        "lime_tea": ("Lime Tea", "Tea", "400ml"),
        "honey_lemon_tea": ("Honey Lemon Tea", "Tea", "400ml"),
        "honey_lime_tea": ("Honey Lime Tea", "Tea", "400ml"),
        "honey_tea_o": ("Honey Tea O", "Tea", "400ml"),
        "honey_milk_tea": ("Honey Milk Tea", "Tea", "400ml"),
        "almond_tea_o": ("Almond Tea O", "Tea", "400ml"),
        "almond_milk_tea": ("Almond Milk Tea", "Tea", "400ml"),
        "almond_milk_tea_c": ("Almond Milk Tea C", "Tea", "400ml"),
        "ginger_tea_o": ("Ginger Tea O", "Tea", "400ml"),
        "ginger_milk_tea": ("Ginger Milk Tea", "Tea", "400ml"),
        "ginger_milk_tea_c": ("Ginger Milk Tea C", "Tea", "400ml"),
        "gula_melaka_milk_tea": ("Gula Melaka Milk Tea", "Tea", "450ml"),
        "gula_melaka_milk_tea_c": ("Gula Melaka Milk Tea C", "Tea", "450ml"),
        "honey_o": ("Honey O", "Honey", "400ml"),
        "honey_lime": ("Honey Lime", "Honey", "400ml"),
        "honey_sour_plum": ("Honey Sour Plum", "Honey", "400ml"),
        "honey_ginger": ("Honey Ginger", "Honey", "400ml"),
        "ginger_o": ("Ginger O", "Tea", "400ml"),
        "sparkling_honey": ("Sparkling Honey", "Sparkling", "450ml"),
        "sparkling_honey_lemon": ("Sparkling Honey Lemon", "Sparkling", "450ml"),
        "sparkling_honey_lime": ("Sparkling Honey Lime", "Sparkling", "450ml"),
        "sparkling_honey_sour_plum": ("Sparkling Honey Sour Plum", "Sparkling", "450ml"),
        "salted_lemon": ("Salted Lemon", "Honey", "450ml"),
        "almond_o": ("Almond O", "Almond", "400ml"),
        "almond_milk": ("Almond Milk", "Almond", "400ml"),
        "milo_o": ("Milo O", "Milo", "400ml"),
        "milo_c": ("Milo C", "Milo", "400ml"),
        "horlicks_o": ("Horlicks O", "Horlicks", "400ml"),
        "horlicks_c": ("Horlicks C", "Horlicks", "400ml"),
        "iced_horlicks_dino": ("Iced Horlicks Dino", "Horlicks", "450ml"),
    }
    drinks = {
        key: Drink(name=name, drink_type=drink_type, default_size=size)
        for key, (name, drink_type, size) in drink_specs.items()
    }
    db.add_all(drinks.values())
    db.flush()

    chain_specs = {
        "yakun": ("Ya Kun Kaya Toast", "https://yakun.com/"),
        "toast_box": ("Toast Box", "https://toastbox.sg/"),
        "luckin": ("Luckin Coffee", "https://www.luckincoffee.com/"),
        "starbucks": ("Starbucks", "https://www.starbucks.com.sg/"),
        "huggs": ("Huggs Coffee", "https://huggscoffee.com/"),
        "fun_toast": ("Fun Toast", "https://www.funtoast.com.sg/"),
        "joe_dough": ("Joe & Dough", "https://www.joeanddough.com/"),
        "alchemist": ("Alchemist", "https://alchemist.global/"),
        "common_man": ("Common Man Coffee Roasters", "https://commonmancoffeeroasters.com/"),
        "coffee_bean": ("The Coffee Bean & Tea Leaf", "https://www.coffeebean.com.sg/"),
        "coffee_break": ("Coffee Break", "https://coffeebreaksg.com/"),
        "tiong_bahru_bakery": ("Tiong Bahru Bakery", "https://www.tiongbahrubakery.com/"),
        "arabica": ("% Arabica", "https://arabica.com/"),
        "kenangan": ("Kenangan Coffee", "https://www.kenangancoffee.sg/"),
        "dalkomm": ("dal.komm Coffee", "https://www.dalkomm.com.sg/"),
        "blue_bottle": ("Blue Bottle Coffee", "https://bluebottlecoffee.com/"),
        "independent": ("Independent", None),
        "food_junction": ("Food Junction", None),
        "prata_alley": ("Prata Alley", None),
        "old_tea_hut": ("Old Tea Hut", "https://oldteahut.com/"),
        "local_coffee_people": ("Local Coffee People", "https://localcoffeepeople.com/"),
    }
    chains = {
        key: Chain(name=name, slug=unique_slug(db, name, Chain), website=website)
        for key, (name, website) in chain_specs.items()
    }
    db.add_all(chains.values())
    db.flush()

    shop_specs = [
        (
            "yakun",
            "Ya Kun Kaya Toast 61 Robinson",
            "61 Robinson",
            "61 Robinson Road #01-01, Singapore 068893",
            "Raffles Place",
        ),
        (
            "yakun",
            "Ya Kun Kaya Toast One Raffles Place",
            "One Raffles Place",
            "1 Raffles Place #B1-13, Singapore 048616",
            "Raffles Place",
        ),
        (
            "yakun",
            "Ya Kun Kaya Toast Hong Leong Building",
            "Hong Leong Building",
            "16 Raffles Quay #B1-46, Singapore 048581",
            "Raffles Place",
        ),
        (
            "yakun",
            "Ya Kun Kaya Toast Raffles City",
            "Raffles City",
            "252 North Bridge Road #B1-05, Singapore 179103",
            "City Hall",
        ),
        (
            "yakun",
            "Ya Kun Kaya Toast 100AM",
            "100AM",
            "100 Tras Street #02-16, Singapore 079027",
            "Tanjong Pagar",
        ),
        (
            "yakun",
            "Ya Kun Kaya Toast Frasers Tower",
            "Frasers Tower",
            "182 Cecil Street #02-06, Singapore 069547",
            "Tanjong Pagar",
        ),
        (
            "toast_box",
            "Toast Box Phillip Street",
            "Phillip Street",
            "3 Phillip Street #01-05, Singapore 048693",
            "Raffles Place",
        ),
        (
            "toast_box",
            "Toast Box Raffles City",
            "Raffles City Shopping Centre",
            "252 North Bridge Road #B1-44A, Singapore 179103",
            "City Hall",
        ),
        (
            "toast_box",
            "Toast Box Marina Bay Link Mall",
            "Marina Bay Link Mall",
            "8A Marina Boulevard #B2-04A, Singapore 018987",
            "Marina Bay",
        ),
        (
            "toast_box",
            "Toast Box Esplanade Mall",
            "Esplanade Mall",
            "8 Raffles Avenue #01-01/03, Singapore 039802",
            "Marina Centre",
        ),
        (
            "toast_box",
            "Toast Box Asia Square",
            "Asia Square",
            "8 Marina View #02-06 Asia Square Tower 1, Singapore 018960",
            "Marina Bay",
        ),
        (
            "toast_box",
            "Toast Box Manulife Tower",
            "Manulife Tower",
            "8 Cross Street #01-K1 Manulife Tower, Singapore 048424",
            "Raffles Place",
        ),
        (
            "toast_box",
            "Toast Box Suntec City",
            "Suntec City",
            "3 Temasek Boulevard Tower 5 #B1-167/168, Singapore 038983",
            "Marina Centre",
        ),
        (
            "luckin",
            "Luckin Coffee One Raffles Place Tower 2",
            "One Raffles Place Tower 2",
            "1 Raffles Place #01-62, Singapore 048616",
            "Raffles Place",
        ),
        (
            "luckin",
            "Luckin Coffee CityLink",
            "CityLink Mall",
            "1 Raffles Link #B1-66, Singapore 039393",
            "City Hall",
        ),
        (
            "luckin",
            "Luckin Coffee Collyer Quay",
            "Collyer Quay",
            "16 Collyer Quay #01-05, Singapore 049318",
            "Raffles Place",
        ),
        (
            "luckin",
            "Luckin Coffee Downtown Core",
            "120 Robinson Road",
            "120 Robinson Road #01-01/01A, Singapore 068913",
            "Downtown Core",
        ),
        (
            "luckin",
            "Luckin Coffee 100AM",
            "100AM",
            "100 Tras Street #01-13A, Singapore 079027",
            "Tanjong Pagar",
        ),
        (
            "luckin",
            "Luckin Coffee Duo Galleria",
            "Duo Galleria",
            "7 Fraser Street #B3-08 Duo Galleria, Singapore 189350",
            "Bugis",
        ),
        (
            "luckin",
            "Luckin Coffee Guoco Tower",
            "Guoco Tower",
            "7 Wallich Street #B1-24 Guoco Tower, Singapore 078884",
            "Tanjong Pagar",
        ),
        (
            "luckin",
            "Luckin Coffee Marina One",
            "Marina One",
            "5 Straits View B2-30 The Heart, Singapore 018935",
            "Marina Bay",
        ),
        (
            "luckin",
            "Luckin Coffee Marina Square",
            "Marina Square",
            "6 Raffles Boulevard #02-153 Marina Square, Singapore 039594",
            "Marina Centre",
        ),
        (
            "luckin",
            "Luckin Coffee Robinson 77",
            "Robinson 77",
            "77 Robinson Road #01-03, Singapore 068896",
            "Tanjong Pagar",
        ),
        (
            "luckin",
            "Luckin Coffee Royal Group Building",
            "Royal Group Building",
            "3 Phillip Street #01-01 Royal Group Building, Singapore 048693",
            "Raffles Place",
        ),
        (
            "luckin",
            "Luckin Coffee South Beach Tower",
            "South Beach Tower",
            "38 Beach Road #01-12A South Beach Tower, Singapore 189767",
            "City Hall",
        ),
        (
            "luckin",
            "Luckin Coffee Suntec City",
            "Suntec City",
            "3 Temasek Boulevard #02-375/376 Suntec City, Singapore 038983",
            "Marina Centre",
        ),
        (
            "starbucks",
            "Starbucks CityLink Mall",
            "CityLink Mall",
            "1 Raffles Link #B1-15/17, Singapore 039393",
            "City Hall",
        ),
        (
            "starbucks",
            "Starbucks Raffles City",
            "Raffles City Shopping Centre",
            "252 North Bridge Road #02-34, Singapore 179103",
            "City Hall",
        ),
        (
            "starbucks",
            "Starbucks 6 Battery Road",
            "6 Battery Road",
            "6 Battery Road #01-05, Singapore 049909",
            "Raffles Place",
        ),
        (
            "starbucks",
            "Starbucks 25 North Bridge Road",
            "25 North Bridge Road",
            "25 North Bridge Road #01-01, Singapore 179104",
            "City Hall",
        ),
        (
            "starbucks",
            "Starbucks 78 Shenton Way",
            "78 Shenton Way",
            "78 Shenton Way #01-02, Singapore 079120",
            "Shenton Way",
        ),
        (
            "starbucks",
            "Starbucks 100AM",
            "100AM",
            "100 Tras Street #01-05 100AM, Singapore 079027",
            "Tanjong Pagar",
        ),
        (
            "starbucks",
            "Starbucks One George",
            "One George",
            "1 George Street #01-02, Singapore 049145",
            "Raffles Place",
        ),
        (
            "starbucks",
            "Starbucks Asia Square Tower 2",
            "Asia Square Tower 2",
            "12 Marina View #02-22 Asia Square Tower II, Singapore 018961",
            "Marina Bay",
        ),
        (
            "starbucks",
            "Starbucks Capital Tower",
            "Capital Tower",
            "168 Robinson Road #01-01/02 Capital Tower, Singapore 068912",
            "Tanjong Pagar",
        ),
        (
            "starbucks",
            "Starbucks Guoco Tower",
            "Guoco Tower",
            "7 Wallich Street #01-08 Guoco Tower, Singapore 078884",
            "Tanjong Pagar",
        ),
        (
            "starbucks",
            "Starbucks Marina Bay Link Mall",
            "Marina Bay Link Mall",
            "8A Marina Boulevard #B2-38-36 Marina Bay Link Mall, Singapore 018984",
            "Marina Bay",
        ),
        (
            "huggs",
            "Huggs Coffee GB Building",
            "GB Building",
            "143 Cecil Street #01-00, Singapore 069542",
            "Tanjong Pagar",
        ),
        (
            "huggs",
            "Huggs Coffee The Clift",
            "The Clift",
            "21 McCallum Street #01-07/08, Singapore 069047",
            "Telok Ayer",
        ),
        (
            "huggs",
            "Huggs Coffee Millenia Walk",
            "Millenia Walk",
            "9 Raffles Boulevard #01-92, Singapore 039596",
            "Marina Centre",
        ),
        (
            "huggs",
            "Huggs Coffee International Plaza",
            "International Plaza",
            "10 Anson Road #01-48, Singapore 079903",
            "Tanjong Pagar",
        ),
        (
            "huggs",
            "Huggs Coffee Great Eastern Centre",
            "Great Eastern Centre",
            "1 Pickering Street #01-03, Singapore 048659",
            "Raffles Place",
        ),
        (
            "huggs",
            "Huggs Coffee Maxwell",
            "Maxwell",
            "30 Maxwell Road #01-03, Singapore 069114",
            "Tanjong Pagar",
        ),
        (
            "fun_toast",
            "Fun Toast Raffles Place MRT",
            "Raffles Place MRT",
            "5 Raffles Place #B1-17/21/22, Singapore 048618",
            "Raffles Place",
        ),
        (
            "fun_toast",
            "Fun Toast One Raffles Place",
            "One Raffles Place",
            "1 Raffles Place #B1-02, Singapore 048616",
            "Raffles Place",
        ),
        (
            "fun_toast",
            "Fun Toast One Shenton",
            "One Shenton",
            "1 Shenton Way #01-10, Singapore 068803",
            "Shenton Way",
        ),
        (
            "fun_toast",
            "Fun Toast Tanjong Pagar Centre",
            "Tanjong Pagar Centre",
            "7 Wallich Street #B2-17, Singapore 078884",
            "Tanjong Pagar",
        ),
        (
            "fun_toast",
            "Fun Toast Marina One",
            "Marina One",
            "5 Straits View #B2-45A, Singapore 018935",
            "Marina Bay",
        ),
        (
            "fun_toast",
            "Fun Toast The Clift",
            "The Clift",
            "21 McCallum Street #01-09/10, Singapore 069047",
            "Telok Ayer",
        ),
        (
            "joe_dough",
            "Joe & Dough Capital Tower",
            "Capital Tower",
            "168 Robinson Road Level 36, Singapore 068912",
            "Tanjong Pagar",
        ),
        (
            "joe_dough",
            "Joe & Dough Republic Plaza",
            "Republic Plaza",
            "9 Raffles Place #02-03, Singapore 048619",
            "Raffles Place",
        ),
        (
            "joe_dough",
            "Joe & Dough CapitaSky",
            "CapitaSky",
            "79 Robinson Road #02-03 Bridge+, Singapore 068897",
            "Tanjong Pagar",
        ),
        (
            "joe_dough",
            "Joe & Dough Marina One",
            "Marina One",
            "5 Straits View #B2-12 The Heart, Singapore 018935",
            "Marina Bay",
        ),
        (
            "joe_dough",
            "Joe & Dough Maybank Tower",
            "Maybank Tower",
            "2 Battery Road #01-01, Singapore 049907",
            "Raffles Place",
        ),
        (
            "alchemist",
            "Alchemist International Plaza",
            "International Plaza",
            "10 Anson Road #01-34 International Plaza, Singapore 079903",
            "Tanjong Pagar",
        ),
        (
            "alchemist",
            "Alchemist Robinson Road",
            "Robinson Road",
            "71 Robinson Road #01-01, Singapore 068895",
            "Raffles Place",
        ),
        (
            "common_man",
            "Common Man Coffee Roasters Stanley Street",
            "Stanley Street",
            "11-12 Stanley Street, Singapore 068730",
            "Telok Ayer",
        ),
        (
            "coffee_bean",
            "The Coffee Bean & Tea Leaf Change Alley Mall",
            "Change Alley Mall",
            "30 Raffles Place #01-09 CIMB Plaza, Singapore 048622",
            "Raffles Place",
        ),
        (
            "coffee_break",
            "Coffee Break Amoy Street",
            "Amoy Street Food Centre",
            "7 Maxwell Road #02-78, Singapore 069111",
            "Tanjong Pagar",
        ),
        (
            "coffee_break",
            "Coffee Break Market Street",
            "Market Street Hawker Centre",
            "86 Market Street #03-03, Singapore 048947",
            "Raffles Place",
        ),
        (
            "tiong_bahru_bakery",
            "Tiong Bahru Bakery Raffles City",
            "Raffles City",
            "252 North Bridge Road #B1-11, Singapore 179103",
            "City Hall",
        ),
        (
            "tiong_bahru_bakery",
            "Tiong Bahru Bakery Funan",
            "Funan",
            "107 North Bridge Road #04-22/25, Singapore 179105",
            "City Hall",
        ),
        (
            "arabica",
            "% Arabica CapitaSpring",
            "CapitaSpring",
            "88 Market Street #01-K2, Singapore 048948",
            "Raffles Place",
        ),
        (
            "kenangan",
            "Kenangan Coffee Raffles City",
            "Raffles City",
            "252 North Bridge Road #B1-78, Singapore 179103",
            "City Hall",
        ),
        (
            "dalkomm",
            "dal.komm Coffee Marina Square",
            "Marina Square",
            "6 Raffles Boulevard #02-278, Singapore 039594",
            "Marina Centre",
        ),
        (
            "blue_bottle",
            "Blue Bottle Coffee Raffles City",
            "Raffles City",
            "252 North Bridge Road #01-22A, Singapore 179103",
            "City Hall",
        ),
        (
            "independent",
            "Bras Basah Food Court",
            "Bras Basah Complex",
            "231 Bain St, #01-79, Complex 180231",
            "City Hall MRT",
        ),
        (
            "food_junction",
            "Toast Junction",
            "Food Place",
            "252 North Bridge Road #03-15/16/17 Raffles City Shopping Centre, Singapore 179103",
            "City Hall",
        ),
        (
            "prata_alley",
            "Open Kitchen by Prata Alley",
            "Singapore Management University (SMU)",
            "40 Stamford Road, #01-01 SMU Connexion, Singapore 178908",
            "Bras Basah",
        ),
        (
            "old_tea_hut",
            "Old Tea Hut One Raffles Place",
            "One Raffles Place",
            "1 Raffles Place #B1-15, Singapore 048616",
            "Raffles Place",
        ),
        (
            "old_tea_hut",
            "Old Tea Hut Marina Bay Link Mall",
            "Marina Bay Link Mall",
            "8A Marina Boulevard #B2-70, Singapore 018984",
            "Marina Bay",
        ),
        (
            "old_tea_hut",
            "Old Tea Hut Robinson 77",
            "Robinson 77",
            "77 Robinson Road #01-02A, Singapore 068896",
            "Tanjong Pagar",
        ),
        (
            "old_tea_hut",
            "Old Tea Hut Downtown Gallery",
            "Downtown Gallery",
            "6A Shenton Way #03-27, Singapore 068815",
            "Shenton Way",
        ),
        (
            "old_tea_hut",
            "Old Tea Hut MAS Building",
            "Monetary Authority of Singapore",
            "10 Shenton Way #01-K2, Singapore 079117",
            "Shenton Way",
        ),
        (
            "local_coffee_people",
            "Local Coffee People 120 Robinson Road",
            "120 Robinson Road",
            "120 Robinson Road #02-01, Singapore 068913",
            "Tanjong Pagar",
        ),
        (
            "local_coffee_people",
            "Local Coffee People CIMB Plaza",
            "CIMB Plaza",
            "30 Raffles Place #B1-18, Singapore 048622",
            "Raffles Place",
        ),
        (
            "local_coffee_people",
            "Local Coffee People International Plaza",
            "International Plaza",
            "10 Anson Road #01-55, Singapore 079903",
            "Tanjong Pagar",
        ),
        (
            "local_coffee_people",
            "Local Coffee People The Sail",
            "The Sail",
            "2 Marina Boulevard #B1-08, Singapore 018987",
            "Marina Bay",
        ),
        (
            "local_coffee_people",
            "Local Coffee People Capital Square 3",
            "Capital Square 3",
            "25 Church Street #01-08, Singapore 049482",
            "Raffles Place",
        ),
        (
            "local_coffee_people",
            "Local Coffee People Income at Raffles",
            "Income at Raffles",
            "16 Collyer Quay #01-14, Singapore 049318",
            "Raffles Place",
        ),
        (
            "local_coffee_people",
            "Local Coffee People Republic Plaza",
            "Republic Plaza",
            "9 Raffles Place #B1-03, Singapore 048619",
            "Raffles Place",
        ),
        (
            "local_coffee_people",
            "Steam by Local Coffee People Ocean Financial Centre",
            "Ocean Financial Centre",
            "10 Collyer Quay #B1-10, Singapore 049315",
            "Raffles Place",
        ),
        (
            "local_coffee_people",
            "Steam by Local Coffee People Marina One",
            "Marina One",
            "5 Straits View #B2-31 The Heart, Singapore 018935",
            "Marina Bay",
        ),
        (
            "local_coffee_people",
            "Steam by Local Coffee People One Raffles Place",
            "One Raffles Place",
            "1 Raffles Place #02-27, Singapore 048616",
            "Raffles Place",
        ),
    ]
    shops = [
        Shop(
            name=name,
            location=location,
            address=address,
            neighborhood=neighborhood,
            chain_id=chains[chain_key].id,
        )
        for chain_key, name, location, address, neighborhood in shop_specs
    ]
    db.add_all(shops)
    db.flush()

    template_prices = {
        "yakun": {
            "kopi": "2.00",
            "kopi_o": "1.80",
            "kopi_c": "2.20",
            "iced_coffee": "2.90",
            "iced_coffee_o": "2.80",
            "iced_coffee_c": "3.10",
            "iced_yuan_yang": "3.00",
        },
        "toast_box": {
            "kopi": "3.40",
            "kopi_o": "3.30",
            "kopi_c": "3.40",
            "iced_coffee": "3.40",
            "iced_coffee_o": "3.40",
            "iced_coffee_c": "3.40",
            "yuan_yang": "3.50",
            "kopi_melaka": "4.30",
        },
        "luckin": {
            "coconut_latte": "6.40",
            "iced_minty_coconut_latte": "6.80",
            "creamy_dreamy_latte": "6.40",
            "toffee_hazelnut_latte": "6.40",
            "creme_brule_latte": "6.80",
            "big_cheese_latte": "6.40",
        },
        "starbucks": {
            "caffe_latte": "7.50",
            "iced_caffe_latte": "7.10",
            "caffe_americano": "6.10",
            "caramel_macchiato": "8.40",
            "white_chocolate_mocha": "7.80",
            "vanilla_sweet_cream_cold_brew": "8.40",
        },
        "huggs": {
            "caffe_latte": "6.90",
            "flat_white": "6.40",
            "cappuccino": "6.90",
            "mocha": "7.50",
            "americano": "5.80",
            "white_americano": "5.80",
            "hazelnut_latte": "7.40",
            "vanilla_latte": "7.40",
            "caramel_latte": "7.40",
            "archipelago_cold_brew": "6.40",
            "latte_gula": "7.50",
            "kopi": "3.20",
            "kopi_c": "3.40",
            "kopi_o": "2.80",
            "iced_kopi_grande": "4.50",
            "iced_kopi_c_grande": "4.80",
            "iced_kopi_o_grande": "4.30",
        },
        "fun_toast": {
            "fun_coffee": "2.10",
            "fun_coffee_o": "2.00",
            "fun_coffee_c": "2.20",
            "yuan_yang": "2.30",
            "gula_melaka_coffee": "2.50",
        },
        "joe_dough": {
            "piccolo_latte": "6.50",
            "americano": "6.50",
            "flat_white": "7.30",
            "cappuccino": "7.30",
            "caffe_latte": "7.30",
            "vanilla_latte": "7.80",
            "hazelnut_latte": "7.80",
            "manuka_honey_latte": "8.00",
            "mocha": "7.80",
            "dr_joe": "7.80",
            "avocado_cafe_latte": "8.00",
            "dirty_matcha": "7.80",
        },
        "alchemist": {
            "espresso": "3.50",
            "batch_brew": "3.50",
            "black_coffee": "5.00",
            "iced_black": "6.00",
            "white_coffee": "5.50",
            "iced_white": "6.50",
            "mocha": "6.00",
            "iced_mocha": "7.00",
        },
        "common_man": {
            "black_coffee": "5.50",
            "flat_white": "7.00",
            "cappuccino": "7.00",
            "caffe_latte": "7.00",
            "mocha": "8.00",
            "archipelago_cold_brew": "8.50",
            "iced_americano": "6.50",
            "iced_latte": "8.00",
        },
        "coffee_bean": {
            "caffe_latte": "8.20",
            "oat_milk_latte": "8.50",
            "flat_white": "8.50",
            "mocha_latte": "8.50",
            "vanilla_latte": "8.50",
            "hazelnut_latte": "8.50",
            "salted_caramel_latte": "8.60",
            "spanish_latte": "7.90",
        },
        "coffee_break": {
            "kopi": "1.80",
            "kopi_o": "1.60",
            "kopi_c": "2.00",
            "iced_coffee": "2.50",
            "sea_salt_caramel_latte": "4.00",
            "black_sesame_latte": "4.00",
            "butter_pecan_latte": "4.00",
            "taro_milk_latte": "4.00",
        },
        "tiong_bahru_bakery": {
            "espresso": "4.50",
            "macchiato": "4.70",
            "long_black": "4.50",
            "batch_brew": "4.70",
            "piccolo_latte": "4.70",
            "magic": "5.20",
            "flat_white": "5.20",
            "cappuccino": "5.20",
            "caffe_latte": "5.20",
            "mocha": "6.40",
        },
        "arabica": {
            "espresso": "4.80",
            "espresso_macchiato": "5.80",
            "caffe_latte": "7.00",
            "iced_caffe_latte": "8.00",
            "americano": "6.00",
            "iced_americano": "6.60",
            "spanish_latte": "7.80",
            "dark_latte": "8.60",
            "kyoto_latte": "7.80",
        },
        "kenangan": {
            "americano": "3.90",
            "espresso": "2.90",
            "caffe_latte": "4.50",
            "cappuccino": "4.50",
            "kenangan_latte": "4.90",
            "creamy_latte": "4.90",
            "creamy_aren_latte": "4.90",
            "vanilla_latte": "4.90",
            "hazelnut_latte": "4.90",
            "salted_caramel_latte": "5.50",
            "mocha": "6.00",
            "avocado_coffee": "6.50",
        },
        "dalkomm": {
            "espresso": "5.90",
            "macchiato": "5.90",
            "americano": "6.40",
            "caffe_latte": "8.20",
            "cappuccino": "8.20",
            "flat_white": "8.20",
            "vanilla_latte": "8.70",
            "mocha": "8.70",
            "caramel_latte": "8.70",
            "rose_latte": "8.70",
            "piccolo_latte": "8.20",
            "coffee_cube": "9.70",
            "honey_coffee_cube": "9.70",
        },
        "blue_bottle": {
            "americano": "6.50",
            "cold_brew": "7.50",
            "drip_coffee": "10.00",
            "gibraltar": "7.50",
            "macchiato": "7.00",
            "caffe_latte": "7.50",
            "cappuccino": "7.50",
        },
        "independent": {
            "kopi_o": "2.00",
            "kopi_c": "2.00",
            "iced_coffee_o": "2.60",
            "iced_coffee_c": "2.60",
            "yuan_yang": "2.00",
            "iced_yuan_yang": "2.60",
            "iced_kopi_grande": "2.60",
            "iced_kopi_c_grande": "2.60",
            "iced_kopi_o_grande": "2.60",
            "fun_coffee_o": "2.00",
            "fun_coffee_c": "2.00",
        },
        "food_junction": {
            "iced_coffee": "2.60",
            "iced_coffee_o": "2.50",
            "iced_coffee_c": "2.70",
            "yuan_yang": "2.00",
            "iced_yuan_yang": "2.70",
            "fun_coffee": "1.90",
            "fun_coffee_o": "1.80",
            "fun_coffee_c": "2.00",
            "tea_o": "1.80",
            "teh": "1.90",
            "teh_c": "2.00",
            "milo": "2.20",
            "iced_milo": "2.90",
            "iced_tea_o": "2.50",
            "iced_tea": "2.70",
            "iced_teh_c": "2.70",
            "iced_milo_dinosaur": "3.40",
            "horlicks": "2.20",
            "iced_horlicks": "2.90",
            "homemade_iced_lemon_tea": "2.60",
            "homemade_lemon_tea": "2.00",
            "honey_water": "2.20",
            "iced_honey_water": "2.70",
            "barley": "1.80",
            "iced_barley": "1.80",
            "iced_calamansi_tea": "2.60",
            "iced_lime_juice_sour_plum": "2.40",
        },
        "prata_alley": {
            "kopi_o": "1.80",
            "iced_coffee_o": "2.40",
            "tea_o": "1.60",
            "iced_tea_o": "2.20",
            "iced_milo_dinosaur": "4.00",
            "teh_tarik": "1.80",
            "kopi_tarik": "1.80",
            "honey_lemon": "2.30",
            "iced_honey_lemon": "2.90",
        },
        "old_tea_hut": {
            "fun_coffee_o": "2.10",
            "fun_coffee": "2.20",
            "fun_coffee_c": "2.30",
            "yuan_yang_o": "1.00",
            "yuan_yang": "2.60",
            "yuan_yang_c": "2.60",
            "honey_coffee_o": "2.70",
            "honey_milk_coffee": "2.70",
            "almond_coffee_o": "2.70",
            "almond_milk_coffee": "2.70",
            "almond_milk_coffee_c": "2.70",
            "gula_melaka_milk_coffee": "3.00",
            "gula_melaka_milk_coffee_c": "3.00",
            "tea_o": "2.10",
            "teh": "2.20",
            "teh_c": "2.30",
            "lemon_tea": "2.70",
            "honey_lemon_tea": "2.80",
            "lime_tea": "2.70",
            "honey_lime_tea": "2.80",
            "honey_tea_o": "2.60",
            "honey_milk_tea": "2.70",
            "almond_tea_o": "2.70",
            "almond_milk_tea": "2.70",
            "almond_milk_tea_c": "2.70",
            "ginger_tea_o": "2.70",
            "ginger_milk_tea": "2.70",
            "ginger_milk_tea_c": "2.70",
            "gula_melaka_milk_tea": "3.00",
            "gula_melaka_milk_tea_c": "3.00",
            "honey_o": "2.30",
            "honey_lemon": "2.70",
            "honey_lime": "2.70",
            "honey_sour_plum": "2.70",
            "honey_ginger": "2.70",
            "ginger_o": "2.50",
            "sparkling_honey": "4.00",
            "sparkling_honey_lemon": "4.30",
            "sparkling_honey_lime": "4.30",
            "sparkling_honey_sour_plum": "4.30",
            "salted_lemon": "3.80",
            "almond_o": "2.50",
            "almond_milk": "2.70",
            "milo_o": "2.80",
            "milo_c": "2.80",
            "iced_milo_dinosaur": "4.20",
            "horlicks_o": "2.80",
            "horlicks_c": "2.80",
            "iced_horlicks_dino": "4.20",
        },
        "local_coffee_people": {
            "fun_coffee": "1.80",
            "fun_coffee_o": "1.50",
            "fun_coffee_c": "1.70",
            "iced_coffee": "2.40",
            "iced_coffee_o": "2.30",
            "iced_coffee_c": "2.50",
            "teh": "1.80",
            "tea_o": "1.50",
            "teh_c": "1.70",
            "iced_tea": "2.40",
            "iced_tea_o": "2.30",
            "iced_teh_c": "2.50",
            "yuan_yang": "2.00",
            "iced_yuan_yang": "2.70",
            "honey_lemon_tea": "2.70",
            "honey_lime": "2.70",
            "honey_tea_o": "2.50",
            "ginger_milk_tea": "2.70",
            "almond_milk_coffee": "2.70",
            "gula_melaka_milk_coffee": "3.00",
            "gula_melaka_milk_tea": "3.00",
            "salted_lemon": "3.80",
            "honey_sour_plum": "2.70",
            "honey_milk_tea": "2.70",
            "milo": "2.20",
            "iced_milo_dinosaur": "4.00",
        },
    }

    template_notes = {
        "independent": {
            "kopi_o": "Student $0.40 off",
            "kopi_c": "Student $0.40 off",
            "iced_coffee_o": "Student $0.30 off",
            "iced_coffee_c": "Student $0.30 off",
            "yuan_yang": "Student $0.40 off",
            "iced_yuan_yang": "Student $0.30 off",
            "iced_kopi_grande": "Student $0.30 off",
            "iced_kopi_c_grande": "Student $0.30 off",
            "iced_kopi_o_grande": "Student $0.30 off",
            "fun_coffee_o": "Student $0.40 off",
            "fun_coffee_c": "Student $0.40 off",
        },
        "food_junction": {
            "iced_coffee": "$3.30 for big",
            "iced_coffee_o": "$3.20 for big",
            "iced_coffee_c": "$3.40 for big",
            "yuan_yang": "$2.40 for big",
            "iced_yuan_yang": "$3.40 for big",
            "fun_coffee": "$2.30 for big",
            "fun_coffee_o": "$2.20 for big",
            "fun_coffee_c": "$2.30 for big",
            "tea_o": "$2.20 for big",
            "teh": "$2.30 for big",
            "teh_c": "$2.40 for big",
            "milo": "$2.60 for big",
            "iced_milo": "$3.50 for big",
            "iced_tea_o": "$3.20 for big",
            "iced_tea": "$3.40 for big",
            "iced_teh_c": "$3.40 for big",
            "iced_milo_dinosaur": "$4 for big",
            "horlicks": "$2.60 for big",
            "iced_horlicks": "$3.50 for big",
            "homemade_iced_lemon_tea": "$3.30 for big",
            "homemade_lemon_tea": "$2.40 for big",
            "honey_water": "$2.60 for big",
            "iced_honey_water": "$3.40 for big",
            "barley": "Iced",
            "iced_calamansi_tea": "$3.30 for big",
            "iced_lime_juice_sour_plum": "$3 for big",
        },
        "prata_alley": {
            "teh_tarik": "$0.60 for ice",
            "kopi_tarik": "$0.60 for ice",
        },
    }

    for chain_key, prices in template_prices.items():
        menu = get_or_create_chain_template_menu(db, chains[chain_key])
        for drink_key, amount in prices.items():
            drink = drinks[drink_key]
            add_or_update_menu_item(
                db,
                menu,
                drink=drink,
                amount=Decimal(amount),
                size_label=drink.default_size,
                notes=template_notes.get(chain_key, {}).get(drink_key, SOURCE_NOTES[chain_key]),
                user=admin,
                overwrite_existing=True,
                price_is_override=False,
            )

    for shop in shops:
        get_or_create_outlet_menu(db, shop)

    for chain in chains.values():
        sync_template_to_outlets(db, chain=chain, user=admin)

    if admin:
        record_audit(
            db,
            admin,
            AuditAction.create,
            "seed",
            None,
            "Loaded sourced Singapore CBD coffee chain data",
            None,
            {
                "checked_on": CHECKED_ON,
                "chains": len(chains),
                "shops": len(shops),
                "drinks": len(drinks),
                "note": "Prices are sourced seed data and should be verified in-store.",
            },
        )
    db.commit()
    return True


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def main() -> None:
    from app.database import SessionLocal, create_db

    parser = argparse.ArgumentParser(description="Seed the CBD coffee directory.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop local tables before seeding. Use only for development data refreshes.",
    )
    args = parser.parse_args()

    if args.reset:
        reset_database()
    else:
        create_db()

    with SessionLocal() as db:
        created = seed_database(db)
    print("Seeded sourced coffee data." if created else "Seed data already present.")


if __name__ == "__main__":
    main()
