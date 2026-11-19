"""
Демо-дані, щоб API одразу було живим: користувачі, категорії, реальні місця Києва, Львова
й Одеси, відгуки, реакції, перегляди за два тижні та підписки.

Відгуки, реакції й підписки створюються через ORM, а не services: сервіс відгуку ставить
у Celery листи автору й підписникам, і сід засипав би Mailpit десятками повідомлень.
Бізнес-правила (не на власну локацію, один відгук/голос на користувача) дотримано тут.
"""

import random
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.locations.models import Category, Location, LocationView
from apps.notifications.models import LocationSubscription
from apps.reviews.models import Review, ReviewReaction
from apps.users.models import User

DEMO_DOMAIN = "@demo.local"
ADMIN_EMAIL = f"admin{DEMO_DOMAIN}"
DEFAULT_PASSWORD = "demo12345"  # noqa: S105 — демо-пароль, лише при DEBUG
VIEWS_HISTORY_DAYS = 14

ADMIN_USERNAME = "admin"
USERNAMES = ["olena", "taras", "iryna", "andrii", "sofiia", "bohdan", "kateryna", "maksym"]
DEMO_USERNAMES = [ADMIN_USERNAME, *USERNAMES]

CATEGORIES = {
    "parks": "Парки",
    "museums": "Музеї",
    "cafes": "Кав'ярні",
    "restaurants": "Ресторани",
    "viewpoints": "Оглядові майданчики",
    "landmarks": "Пам'ятки",
}


@dataclass(frozen=True)
class DemoLocation:
    name: str
    category: str
    address: str
    latitude: str
    longitude: str
    description: str
    # «Справжня» середня оцінка, навколо якої генеруються відгуки; None — без відгуків.
    quality: float | None
    deleted: bool = False


LOCATIONS = [
    DemoLocation(
        "Києво-Печерська лавра",
        "landmarks",
        "вул. Лаврська, 15, Київ",
        "50.434500",
        "30.557100",
        "Православний монастир XI століття, печери та дзвіниця.",
        4.8,
    ),
    DemoLocation(
        "Софійський собор",
        "landmarks",
        "вул. Володимирська, 24, Київ",
        "50.452900",
        "30.514300",
        "Собор XI століття з мозаїками та фресками, об'єкт ЮНЕСКО.",
        4.7,
    ),
    DemoLocation(
        "Андріївська церква",
        "landmarks",
        "Андріївський узвіз, 23, Київ",
        "50.459000",
        "30.517900",
        "Барокова церква Растреллі над Подолом.",
        4.5,
    ),
    DemoLocation(
        "Маріїнський парк",
        "parks",
        "вул. Михайла Грушевського, Київ",
        "50.446700",
        "30.537500",
        "Тінистий парк біля Маріїнського палацу.",
        4.2,
    ),
    DemoLocation(
        "Ботанічний сад імені Гришка",
        "parks",
        "вул. Садово-Ботанічна, 1, Київ",
        "50.413900",
        "30.564300",
        "Бузковий сад навесні й краєвиди на Видубичі.",
        4.6,
    ),
    DemoLocation(
        "Пейзажна алея",
        "viewpoints",
        "Пейзажна алея, Київ",
        "50.457700",
        "30.512300",
        "Арт-об'єкти, дитячі мозаїки та вид на Поділ.",
        4.4,
    ),
    DemoLocation(
        "Міст Кличка",
        "viewpoints",
        "Парковий міст, Київ",
        "50.455500",
        "30.534700",
        "Скляний пішохідний міст із видом на Дніпро.",
        3.4,
    ),
    DemoLocation(
        "Національний художній музей",
        "museums",
        "вул. Михайла Грушевського, 6, Київ",
        "50.449300",
        "30.530600",
        "Українське мистецтво від ікон до авангарду.",
        4.5,
    ),
    DemoLocation(
        "Мистецький арсенал",
        "museums",
        "вул. Лаврська, 10-12, Київ",
        "50.439300",
        "30.553800",
        "Великі виставки сучасного мистецтва в старому арсеналі.",
        4.1,
    ),
    DemoLocation(
        "Музей однієї вулиці",
        "museums",
        "Андріївський узвіз, 2б, Київ",
        "50.464400",
        "30.517100",
        "Історія Андріївського узвозу в речах його мешканців.",
        None,
    ),
    DemoLocation(
        "Кав'ярня на Рейтарській",
        "cafes",
        "вул. Рейтарська, 13, Київ",
        "50.452600",
        "30.511000",
        "Спешелті-кава і круасани в серці Старого Києва.",
        4.3,
    ),
    DemoLocation(
        "Ресторан на Хрещатику",
        "restaurants",
        "вул. Хрещатик, 15, Київ",
        "50.447700",
        "30.522700",
        "Туристичне місце з видом на головну вулицю.",
        1.6,
    ),
    DemoLocation(
        "Кав'ярня біля вокзалу",
        "cafes",
        "Вокзальна площа, 1, Київ",
        "50.440900",
        "30.488600",
        "Кава в дорогу між потягами.",
        2.4,
    ),
    DemoLocation(
        "Старий кінотеатр на Подолі",
        "landmarks",
        "вул. Сагайдачного, 25, Київ",
        "50.462300",
        "30.521900",
        "Будівлю закрито на реконструкцію.",
        3.0,
        deleted=True,
    ),
    DemoLocation(
        "Площа Ринок",
        "landmarks",
        "пл. Ринок, Львів",
        "49.841600",
        "24.031600",
        "Серце Старого міста з ратушею та кам'яницями.",
        4.7,
    ),
    DemoLocation(
        "Високий Замок",
        "viewpoints",
        "вул. Замкова, Львів",
        "49.848300",
        "24.039500",
        "Найвища точка міста й панорама на дахи Львова.",
        4.6,
    ),
    DemoLocation(
        "Личаківський цвинтар",
        "museums",
        "вул. Мечникова, 33, Львів",
        "49.831500",
        "24.055400",
        "Музей-заповідник із надгробками XVIII–XX століть.",
        4.4,
    ),
    DemoLocation(
        "Стрийський парк",
        "parks",
        "вул. Стрийська, Львів",
        "49.823900",
        "24.024100",
        "Найбільший парк центру з каскадом ставків.",
        4.0,
    ),
    DemoLocation(
        "Львівська копальня кави",
        "cafes",
        "пл. Ринок, 10, Львів",
        "49.841300",
        "24.032100",
        "Кава зі «шахти» під кам'яницею на площі Ринок.",
        4.2,
    ),
    DemoLocation(
        "Пузата хата на Сихові",
        "restaurants",
        "просп. Червоної Калини, 60, Львів",
        "49.796700",
        "24.060900",
        "Домашня кухня самообслуговування.",
        3.1,
    ),
    DemoLocation(
        "Музей ідей",
        "museums",
        "вул. Валова, 18а, Львів",
        "49.840500",
        "24.034800",
        "Невеликий простір сучасного мистецтва.",
        None,
    ),
    DemoLocation(
        "Кав'ярня на Підвальній",
        "cafes",
        "вул. Підвальна, 3, Львів",
        "49.841900",
        "24.035700",
        "Заклад закрився.",
        3.8,
        deleted=True,
    ),
    DemoLocation(
        "Потьомкінські сходи",
        "landmarks",
        "Приморський бульвар, Одеса",
        "46.488600",
        "30.741300",
        "192 сходинки від бульвару до морського вокзалу.",
        4.5,
    ),
    DemoLocation(
        "Оперний театр",
        "landmarks",
        "пров. Чайковського, 1, Одеса",
        "46.485200",
        "30.741000",
        "Один із найкрасивіших театрів Європи.",
        4.9,
    ),
    DemoLocation(
        "Парк Шевченка",
        "parks",
        "Маркса Аллея, Одеса",
        "46.477600",
        "30.756500",
        "Старий парк над морем зі стадіоном і алеєю Слави.",
        4.1,
    ),
    DemoLocation(
        "Пасаж",
        "landmarks",
        "вул. Дерибасівська, 33, Одеса",
        "46.484200",
        "30.736700",
        "Еклектичний пасаж кінця XIX століття.",
        3.9,
    ),
    DemoLocation(
        "Ланжерон",
        "viewpoints",
        "Ланжеронівський узвіз, Одеса",
        "46.477800",
        "30.762800",
        "Пляж і вид на порт із мосту.",
        3.6,
    ),
    DemoLocation(
        "Ресторан на Аркадії",
        "restaurants",
        "Аркадійська алея, Одеса",
        "46.429700",
        "30.763400",
        "Гучна музика й ціни для туристів.",
        1.9,
    ),
    DemoLocation(
        "Музей морського флоту",
        "museums",
        "вул. Ланжеронівська, 6, Одеса",
        "46.486300",
        "30.742100",
        "Моделі кораблів та історія одеського порту.",
        None,
    ),
    DemoLocation(
        "Кав'ярня на Грецькій",
        "cafes",
        "вул. Грецька, 20, Одеса",
        "46.483200",
        "30.738200",
        "Затишне місце з одеськими десертами.",
        4.4,
    ),
]

COMMENTS = {
    1: [
        "Розчарування: брудно й неприязний персонал.",
        "Не раджу. Витрачений час.",
        "Гірше, ніж очікував, більше не прийду.",
    ],
    2: [
        "Слабко. Є кращі місця поруч.",
        "Переоцінено, ціни не відповідають якості.",
        "Багато людей і мало вражень.",
    ],
    3: [
        "Нормально, але без вау-ефекту.",
        "Можна зайти, якщо поруч.",
        "Середньо: щось сподобалось, щось ні.",
    ],
    4: [
        "Гарне місце, варто відвідати.",
        "Сподобалось, повернусь ще раз.",
        "Атмосферно, лише трохи людно.",
    ],
    5: [
        "Неймовірно! Обов'язково до відвідування.",
        "Одне з найкращих місць у місті.",
        "Ідеально, рекомендую всім друзям.",
    ],
}


class Command(BaseCommand):
    help = "Наповнює базу демо-даними: користувачі, категорії, локації, відгуки, перегляди."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Видалити й створити наново")
        parser.add_argument("--seed", type=int, default=42, help="Seed генератора випадковостей")
        parser.add_argument(
            "--password",
            help=f"Пароль усіх демо-акаунтів (за замовчуванням {DEFAULT_PASSWORD}, лише при DEBUG)",
        )
        parser.add_argument(
            "--allow-production",
            action="store_true",
            help="Дозволити запуск при DEBUG=False (потрібен --password)",
        )

    def handle(
        self, *args, reset: bool, seed: int, password: str | None, allow_production: bool, **options
    ):
        # Створюється суперкористувач, а пароль за замовчуванням є в README.
        if not settings.DEBUG and (not allow_production or password is None):
            raise CommandError(
                "seed_demo створює суперкористувача; при DEBUG=False запускайте лише "
                "з --allow-production і власним --password."
            )
        self.rng = random.Random(seed)  # noqa: S311 — відтворюваність, а не криптографія

        with transaction.atomic():
            if User.objects.filter(email__endswith=DEMO_DOMAIN).exists():
                if not reset:
                    self.stdout.write(
                        self.style.WARNING("Демо-дані вже є. Для перестворення: seed_demo --reset")
                    )
                    return
                self._delete_demo_data()
            taken = sorted(
                User.objects.filter(username__in=DEMO_USERNAMES).values_list("username", flat=True)
            )
            if taken:
                raise CommandError(f"Імена демо-користувачів уже зайняті: {', '.join(taken)}")
            stats = self._create_demo_data(password or DEFAULT_PASSWORD)

        self.stdout.write(self.style.SUCCESS("Демо-дані створено:"))
        for name, count in stats.items():
            self.stdout.write(f"  {name}: {count}")
        # Власний пароль у вивід не потрапляє: він опинився б у логах деплою.
        shown = DEFAULT_PASSWORD if password is None else "<пароль з --password>"
        self.stdout.write(f"Адмін: {ADMIN_EMAIL} / {shown}")
        self.stdout.write(f"Користувач: {USERNAMES[0]}{DEMO_DOMAIN} / {shown}")

    def _delete_demo_data(self) -> None:
        Location.all_objects.filter(author__email__endswith=DEMO_DOMAIN).hard_delete()
        User.objects.filter(email__endswith=DEMO_DOMAIN).delete()
        # Категорії лишаються: їх могли створити й без сіду.

    def _create_demo_data(self, password: str) -> dict[str, int]:
        password_hash = make_password(password)
        admin = User.objects.create(
            email=ADMIN_EMAIL,
            username=ADMIN_USERNAME,
            password=password_hash,
            is_staff=True,
            is_superuser=True,
        )
        users = [
            User.objects.create(
                email=f"{username}{DEMO_DOMAIN}", username=username, password=password_hash
            )
            for username in USERNAMES
        ]
        categories = {
            slug: self._get_or_create_category(slug, name) for slug, name in CATEGORIES.items()
        }

        stats = dict.fromkeys(
            ["users", "categories", "locations", "deleted", "reviews", "reactions", "views"], 0
        )
        stats["users"] = len(users) + 1
        stats["categories"] = len(categories)
        subscribers = [admin, *users]
        for data in LOCATIONS:
            location = Location.objects.create(
                name=data.name,
                description=data.description,
                category=categories[data.category],
                address=data.address,
                latitude=Decimal(data.latitude),
                longitude=Decimal(data.longitude),
                author=self.rng.choice(users),
            )
            stats["locations"] += 1
            reviews = self._create_reviews(location, users, data.quality)
            stats["reviews"] += len(reviews)
            stats["reactions"] += self._create_reactions(reviews, users)
            stats["views"] += self._create_views(location, users, data.quality)
            for user in self.rng.sample(subscribers, self.rng.randint(0, 2)):
                if user.pk != location.author_id:
                    LocationSubscription.objects.create(user=user, location=location)
            if data.deleted:
                location.delete()
                stats["deleted"] += 1
        stats["subscriptions"] = LocationSubscription.objects.filter(
            user__email__endswith=DEMO_DOMAIN
        ).count()
        return stats

    @staticmethod
    def _get_or_create_category(slug: str, name: str) -> Category:
        # name і slug унікальні окремо: категорія могла з'явитися з іншим slug.
        category = Category.objects.filter(Q(slug=slug) | Q(name=name)).first()
        return category or Category.objects.create(slug=slug, name=name)

    def _create_reviews(self, location: Location, users: list[User], quality) -> list[Review]:
        if quality is None:
            return []
        reviewers = [user for user in users if user.pk != location.author_id]
        count = self.rng.randint(2, len(reviewers))
        reviews = []
        for author in self.rng.sample(reviewers, count):
            rating = min(5, max(1, round(self.rng.gauss(quality, 0.7))))
            reviews.append(
                Review.objects.create(
                    location=location,
                    author=author,
                    rating=rating,
                    comment=self.rng.choice(COMMENTS[rating]),
                )
            )
        return reviews

    def _create_reactions(self, reviews: list[Review], users: list[User]) -> int:
        count = 0
        for review in reviews:
            voters = [user for user in users if user.pk != review.author_id]
            for user in self.rng.sample(voters, self.rng.randint(0, 4)):
                like_chance = 0.8 if review.rating >= 3 else 0.4
                value = (
                    ReviewReaction.Value.LIKE
                    if self.rng.random() < like_chance
                    else ReviewReaction.Value.DISLIKE
                )
                ReviewReaction.objects.create(review=review, user=user, value=value)
                count += 1
        return count

    def _create_views(self, location: Location, users: list[User], quality) -> int:
        count = int(self.rng.randint(10, 60) * (quality or 2.0))
        now = timezone.now()
        visitors = [None, None, *(user for user in users if user.pk != location.author_id)]
        views = []
        for _ in range(count):
            user = self.rng.choice(visitors)
            visitor_key = (
                f"user:{user.pk}"
                if user
                else f"anon:10.0.{self.rng.randint(0, 255)}.{self.rng.randint(1, 254)}"
            )
            views.append(LocationView(location=location, user=user, visitor_key=visitor_key))
        LocationView.objects.bulk_create(views)
        # auto_now_add перезаписує created_at при створенні, тож історію задаємо окремо.
        for view in views:
            view.created_at = now - timedelta(
                seconds=self.rng.randint(0, VIEWS_HISTORY_DAYS * 24 * 3600)
            )
        LocationView.objects.bulk_update(views, ["created_at"], batch_size=500)
        return count
