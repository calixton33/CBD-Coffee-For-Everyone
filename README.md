# CBD Coffee Price Directory

A full-stack FastAPI application for tracking, comparing, and maintaining coffee prices across Singapore Central Business District shops and chain outlets.

The project is designed as a practical price directory: shoppers can search coffee options, compare drink prices across outlets, and use a dashboard to see each shop's average menu price. Editors can add shops, manage drinks, copy menus between outlets, sync chain template menus, and review an audit log of changes.

## Screenshot

![Average price dashboard](docs/screenshots/dashboard.png)

## Tech Stack

- FastAPI and Jinja templates
- SQLAlchemy ORM
- SQLite for local development
- PostgreSQL-ready through `DATABASE_URL`
- Vanilla JavaScript, HTML, and CSS
- Pytest

## Features

- Public directory of CBD coffee shops and outlet menus
- Dashboard with average price, cheapest drink, and priciest drink by shop
- Drink-level price comparison across shops
- Search by shop, drink, location, or chain
- Price range filters and sorting by price, shop, drink type, or chain
- Chain detection when a shop is added with an existing chain-like name
- Chain outlet grouping
- Chain template menus
- Menu duplication from one outlet to another
- Full-menu or selected-drink copy support
- Template sync to outlets while preserving outlet price overrides by default
- Editor-key authentication for all writes
- Protected audit log with editor, action, entity, and timestamp metadata

## Resume Highlights

- Built REST API endpoints for directory search, price comparison, editor workflows, and shop-level analytics.
- Modeled shops, chains, drinks, menus, prices, users, and audit history with SQLAlchemy relationships.
- Added duplicate-shop detection and chain-aware menu workflows to reduce messy data entry.
- Implemented editor-key authentication and audit logging so write actions are attributable.
- Seeded the app with sourced Singapore CBD coffee data for a realistic demo dataset.

## Project Structure

```text
app/
  main.py                 FastAPI app, startup, router registration
  models.py               SQLAlchemy database schema
  schemas.py              Request and validation schemas
  auth.py                 Editor-key authentication
  audit.py                Audit snapshot and write helpers
  seed.py                 Sourced CBD coffee chain seed data
  services/
    menus.py              Chain detection, menu copy/sync, price history logic
  routers/
    users.py              Editor identity and admin user creation
    shops.py              Directory, shop CRUD, comparison, outlet menu copy
    drinks.py             Drink CRUD
    chains.py             Chain CRUD, template menus, sync, duplication
    menus.py              Menu item edits and price deletion
    audit_log.py          Audit log API
  static/
    css/styles.css        Responsive frontend styles
    js/app.js             Browser UI and API calls
  templates/
    index.html            Main application page
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.seed
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8001/>.

The app auto-creates tables and seeds sourced development data on startup when `AUTO_SEED=true`.
To refresh an existing local SQLite database after seed-data changes, run:

```bash
python -m app.seed --reset
```

## Seed Data Sources

Seed prices were last checked on 2026-06-08 and should be verified in-store before production use. The seeded chains are Ya Kun Kaya Toast, Toast Box, Luckin Coffee, Starbucks, Huggs Coffee, Fun Toast, Joe & Dough, Alchemist, Common Man Coffee Roasters, The Coffee Bean & Tea Leaf, Coffee Break, Tiong Bahru Bakery, % Arabica, Kenangan Coffee, dal.komm Coffee, Blue Bottle Coffee, Old Tea Hut, Local Coffee People, and user-maintained local observations for Bras Basah Food Court, Toast Junction, and Open Kitchen by Prata Alley.

- Ya Kun outlets: <https://yakun.com/find-us/>
- Ya Kun prices: <https://drinkwhisper.com/ya-kuns-drink-menu-with-prices/>
- Toast Box outlets: <https://toastbox.sg/locations/>
- Toast Box Asia Square outlet: <https://toastbox.com.sg/store/asia-square/>
- Toast Box Suntec City outlet: <https://toastbox.com.sg/store/suntec-city/>
- Toast Box prices: <https://drinkwhisper.com/toast-box-drinks-menu-with-prices/>
- Luckin Coffee CBD outlets: <https://sg.syioknya.com/location/company/luckin-coffee/downtown-core/>
- Luckin Coffee prices: <https://sgrestaurantmenu.org/luckin-coffee-singapore-menu/>
- Starbucks CBD outlets: <https://sg.syioknya.com/location/category/coffee/downtown-core/>
- Starbucks Guoco Tower outlet: <https://sg.syioknya.com/location/outlet/starbucks/starbucks-guoco-tower/>
- Starbucks Marina Bay Link Mall outlet: <https://eatleh.com/outlet/starbucks-marina-bay-link-mall/>
- Starbucks Singapore menu prices: <https://mysgmenu.com/starbucks-singapore-review/>
- Huggs Coffee outlets: <https://huggscoffee.com/pages/find-us>
- Huggs Coffee prices: <https://sgeats.net/huggs-coffee-menu-singapore/>
- Fun Toast One Raffles Place outlet: <https://www.funtoast.com.sg/outlets/fun-toast/one-raffles-place/>
- Fun Toast One Shenton outlet: <https://www.funtoast.com.sg/outlets/fun-toast/one-shenton/>
- Fun Toast prices: <https://sgeats.net/fun-toast-menu-singapore/>
- Joe & Dough outlets: <https://www.joeanddough.com/locations/>
- Joe & Dough prices: <https://sgrestaurantsmenu.com/joe-and-dough-menu/>
- Alchemist outlets: <https://alchemist.global/visit>
- Alchemist prices: <https://sgmenu.org/alchemist-menu/>
- Common Man Coffee Roasters outlets: <https://commonmancoffeeroasters.com/pages/our-locations>
- Common Man Coffee Roasters prices: <https://sgmenuguru.org/common-man-coffee-roasters-menu-singapore/>
- The Coffee Bean & Tea Leaf Change Alley outlet: <https://eatleh.com/outlet/the-coffee-bean-tea-leaf-change-alley-mall/>
- The Coffee Bean & Tea Leaf prices: <https://sg.pricelisto.com/menu-prices/the-coffee-bean-tea-leaf-sg>
- Coffee Break outlets: <https://coffeebreaksg.com/shop/>
- Coffee Break price references: <https://hawkerpedia.com.sg/coffee-break-amoy-street/> and <https://eatbook.sg/coffee-break-amoy-street/>
- Tiong Bahru Bakery Raffles City outlet and prices: <https://rafflescitymall.com/shop/tiong-bahru-bakery>
- Tiong Bahru Bakery official menu and outlets: <https://www.tiongbahrubakery.com/menu-new/tiong-bahru-bakery-menu.html>
- % Arabica CapitaSpring outlet: <https://arabica.com/en/location/arabica-singapore-capitaspring/>
- % Arabica prices: <https://menupro.org/arabica-menu/>
- Kenangan Coffee Raffles City outlet and prices: <https://rafflescitymall.com/shop/kenangan-coffee-raffles-city>
- Kenangan Coffee official menu: <https://www.kenangancoffee.sg/our-menu>
- dal.komm Coffee official Singapore site: <https://www.dalkomm.com.sg/>
- dal.komm Coffee Marina Square prices: <https://deliveroo.com.sg/menu/Singapore/esplanade-marina-square/dalkomm-coffee-marina-square>
- Blue Bottle Coffee Raffles City menu reference: <https://www.shout.sg/blue-bottle-opens-first-permanent-cafe-in-singapore-at-raffles-city-with-coffee-from-6-50-singapore-exclusive-bakes/>
- Bras Basah Food Court, Toast Junction, and Open Kitchen by Prata Alley: user-maintained local demo observations restored from the development database.
- Old Tea Hut outlets: <https://oldteahut.com/storelocator.html>
- Old Tea Hut menu and prices: <https://sgmyfoods.com/old-tea-hut-menu-singapore/> and <https://www.oldteahut.com/images/Old%20Tea%20Hut%20Menu%202018.pdf>
- Local Coffee People outlets and menu items: <https://localcoffeepeople.com/>
- Local Coffee People additional outlet/menu reference: <https://healthyeatwhere.com/local-coffee-people-sg/>

## Editor Keys

Fresh public clones do not seed usable editor keys by default. This prevents a deployed demo from accidentally accepting public write access.

For a local-only demo, set this in your private `.env` before creating or resetting the database:

```text
SEED_DEMO_EDITORS=true
```

Then run:

```bash
python -m app.seed --reset
```

Local demo keys will be:

```text
Demo Admin: local-demo-admin-key
Demo Editor: local-demo-editor-key
```

Do not enable `SEED_DEMO_EDITORS` in production. Set a private `SECRET_KEY`, create private editor keys, and keep real environment values out of Git.

## API Highlights

```text
GET    /api/shops
GET    /api/compare
GET    /api/dashboard/shop-averages
POST   /api/shops
PUT    /api/shops/{shop_id}
DELETE /api/shops/{shop_id}

GET    /api/drinks
POST   /api/drinks
PUT    /api/drinks/{drink_id}
DELETE /api/drinks/{drink_id}

GET    /api/chains
POST   /api/chains/{chain_id}/template/items
POST   /api/chains/{chain_id}/sync-template
POST   /api/chains/{chain_id}/duplicate-menu

POST   /api/shops/{source_shop_id}/copy-menu
PUT    /api/menu-items/{menu_item_id}
DELETE /api/menu-items/{menu_item_id}
DELETE /api/prices/{price_id}

GET    /api/audit       Requires X-Editor-Key
GET    /api/users/me
POST   /api/users
```

## Security Notes

- `.env`, local SQLite databases, virtual environments, caches, and build output are ignored by Git.
- CORS is restricted through `CORS_ORIGINS`; do not use `*` for a public deployment.
- Editor keys are sent through the `X-Editor-Key` header and stored only in browser session storage.
- Audit snapshots are not returned by the public API.
- Use a long random `SECRET_KEY` outside Git before sharing a deployed instance.

## PostgreSQL

Set `DATABASE_URL` to a PostgreSQL URL before starting the app:

```bash
export DATABASE_URL="postgresql+psycopg://coffee:coffee@localhost:5432/coffee_cbd"
uvicorn app.main:app --reload
```

For production, keep `SEED_DEMO_EDITORS=false`, set a strong `SECRET_KEY`, set `CORS_ORIGINS` to the real site origin, and run migrations with a tool such as Alembic.
