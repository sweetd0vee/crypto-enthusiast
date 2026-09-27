"""Idempotently fill a running local API with automotive demo polls.

The catalog is a TV-show slate: drafts, scheduled airings, polls on air,
finished broadcasts and cancellations. Finished and cancelled polls that
need a result are opened just long enough to accept votes, then moved to
their final status. A repeat run skips questions that already exist.
"""

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import Any

# phase, name, duration seconds, show offset seconds (None for drafts),
# options, per-option vote counts (None when the poll has no audience yet).
CatalogRow = tuple[str, str, int, int | None, tuple[str, ...], tuple[int, ...] | None]

CATALOG: tuple[CatalogRow, ...] = (
    (
        "draft",
        "Какую марку смотрите на замену текущей?",
        180,
        None,
        ("BMW", "Mercedes-Benz", "Audi", "Lexus", "Genesis", "Volvo"),
        None,
    ),
    (
        "draft",
        "Какой бюджет реален для первого автомобиля?",
        120,
        None,
        (
            "До 800 тыс. ₽",
            "800 тыс. – 1,5 млн ₽",
            "1,5–2,5 млн ₽",
            "2,5–4 млн ₽",
            "Больше 4 млн ₽",
        ),
        None,
    ),
    (
        "draft",
        "Без какой опции мультимедиа машина уже не та?",
        90,
        None,
        (
            "CarPlay и Android Auto",
            "Штатная навигация",
            "Голосовой помощник",
            "Премиальная акустика",
            "Беспроводная зарядка",
        ),
        None,
    ),
    (
        "draft",
        "Какой цвет кузова закажете без ожидания?",
        60,
        None,
        ("Белый", "Чёрный", "Серый", "Синий", "Красный", "Зелёный", "Бежевый"),
        None,
    ),
    (
        "draft",
        "Где купите следующую машину?",
        300,
        None,
        (
            "У официального дилера",
            "Трейд-ин у дилера",
            "У частника с проверкой",
            "На аукционе",
        ),
        None,
    ),
    (
        "draft",
        "Какой диаметр дисков вам ближе?",
        600,
        None,
        ("16 дюймов", "17 дюймов", "18 дюймов", "19 дюймов", "20 дюймов и больше"),
        None,
    ),
    (
        "draft",
        "Панорамная крыша — берёте?",
        30,
        None,
        ("Беру без разговоров", "Только если не съедает высоту", "Не хочу"),
        None,
    ),
    (
        "draft",
        "Как будете платить за следующую машину?",
        900,
        None,
        ("Свои деньги", "Автокредит", "Рассрочка дилера", "Трейд-ин и доплата"),
        None,
    ),
    (
        "scheduled",
        "Какой электромобиль поставили бы в гараж?",
        120,
        26 * 3600,
        ("Tesla Model 3", "Zeekr 001", "BYD Seal", "Hyundai Ioniq 6", "Porsche Taycan"),
        None,
    ),
    (
        "scheduled",
        "Какая система безопасности важнее в городе?",
        180,
        2 * 3600,
        (
            "Автоторможение",
            "Контроль слепых зон",
            "Адаптивный круиз",
            "Удержание в полосе",
        ),
        None,
    ),
    (
        "scheduled",
        "На эту зиму — шипы или липучка?",
        90,
        6 * 3600,
        ("Шипы", "Липучка", "Всесезонка ещё на сезон", "Пока не решил"),
        None,
    ),
    (
        "scheduled",
        "Кому доверите плановое ТО?",
        150,
        30 * 3600,
        (
            "Официальному дилеру",
            "Независимому сервису",
            "Знакомому мастеру",
            "Сделаю сам",
        ),
        None,
    ),
    (
        "scheduled",
        "Гибрид или чистый электро на каждый день?",
        120,
        3 * 86400,
        ("Обычный гибрид", "Подзаряжаемый гибрид", "Чистый электро", "Пока бензин"),
        None,
    ),
    (
        "scheduled",
        "Какому китайскому бренду уже доверяете?",
        240,
        14 * 3600,
        (
            "Haval",
            "Geely",
            "Chery",
            "Changan",
            "Exeed",
            "Zeekr",
            "BYD",
            "Tank",
            "Пока ни одному",
        ),
        None,
    ),
    (
        "scheduled",
        "Нужен ли автопилот в плотной пробке?",
        60,
        4 * 3600,
        ("Нужен", "Хватит адаптивного круиза", "Не доверяю"),
        None,
    ),
    (
        "scheduled",
        "Какой багажник нужен семье из четырёх человек?",
        180,
        2 * 86400,
        (
            "До 400 литров",
            "400–550 литров",
            "Больше 550 литров",
            "Главное — низкий порог",
            "С розеткой в багажнике",
        ),
        None,
    ),
    (
        "scheduled",
        "Дизель в 2026 году ещё имеет смысл?",
        90,
        8 * 3600,
        ("Да, на трассе он ещё уместен", "Нет, больше не рассматриваю"),
        None,
    ),
    (
        "scheduled",
        "Какой тест-драйв вас убедит?",
        45,
        45 * 60,
        (
            "Пятнадцать минут у дилера",
            "Час по городу",
            "Сутки",
            "Выходные с машиной",
        ),
        None,
    ),
    (
        "live",
        "Какой тип кузова практичнее для города?",
        3600,
        -180,
        ("Седан", "Кроссовер", "Хэтчбек", "Универсал", "Лифтбек"),
        (22, 48, 19, 7, 11),
    ),
    (
        "live",
        "Какую коробку выберете и не пожалеете?",
        3600,
        -480,
        ("Классический автомат", "Механика", "Робот", "Вариатор"),
        (41, 16, 6, 9),
    ),
    (
        "live",
        "Что для вас решает при выборе машины?",
        1800,
        -90,
        (
            "Надёжность",
            "Комфорт",
            "Динамика",
            "Экономичность",
            "Дизайн",
            "Как на неё смотрят",
        ),
        (24, 11, 7, 9, 5, 1),
    ),
    (
        "live",
        "Какой японский бренд кажется самым надёжным?",
        2400,
        -720,
        ("Toyota", "Honda", "Mazda", "Subaru", "Lexus", "Nissan"),
        (31, 14, 11, 4, 9, 3),
    ),
    (
        "live",
        "Нужен ли полный привод в вашем городе?",
        1200,
        -120,
        ("Да, каждую зиму", "Да, круглый год", "Хватает переднего", "Только задний"),
        (23, 9, 15, 0),
    ),
    (
        "live",
        "Какой расход топлива ещё не смущает?",
        3600,
        -300,
        (
            "До 6 литров",
            "6–8 литров",
            "8–10 литров",
            "10–12 литров",
            "Больше 12 литров",
            "Считаю киловатты, не литры",
        ),
        (9, 17, 11, 4, 1, 5),
    ),
    (
        "live",
        "Где проходит большая часть ваших поездок?",
        1020,
        -90,
        ("По городу", "По трассе", "Город и трасса поровну", "Редко и недалеко"),
        (18, 3, 9, 1),
    ),
    (
        "live",
        "Какой климат в салоне считаете нормой?",
        3600,
        -900,
        (
            "Одной зоны хватает",
            "Две зоны",
            "Три зоны",
            "Климат не важен",
            "Важнее подогрев сидений",
        ),
        (7, 19, 4, 2, 6),
    ),
    (
        "live",
        "Чем заправляете повседневную машину?",
        2700,
        -400,
        ("Бензин", "Газ", "Гибрид", "Электричество", "Дизель"),
        (26, 3, 15, 11, 7),
    ),
    (
        "live",
        "Что раздражает в современных салонах?",
        1800,
        -200,
        (
            "Сенсор вместо кнопок",
            "Подписки на опции",
            "Автостарт-стоп",
            "Лишние пищалки",
            "Слишком мало кнопок",
            "Глянцевый пластик",
            "Камеры вместо зеркал",
        ),
        (14, 11, 6, 9, 3, 7, 2),
    ),
    (
        "live",
        "Какой кроссовер взяли бы уже завтра?",
        3600,
        -1100,
        (
            "Toyota RAV4",
            "Hyundai Tucson",
            "Haval Jolion",
            "Kia Sportage",
            "Volkswagen Tiguan",
            "Mazda CX-5",
            "Skoda Kodiaq",
        ),
        (16, 9, 13, 10, 6, 12, 5),
    ),
    (
        "live",
        "Запаска в багажнике всё ещё нужна?",
        1500,
        -180,
        ("Полноразмерная", "Докатка", "Ремкомплект", "Только если еду далеко"),
        (11, 6, 4, 5),
    ),
    (
        "closed",
        "Какую марку зрители выбирали в прошлом сезоне?",
        180,
        -(2 * 86400 + 180),
        ("BMW", "Mercedes-Benz", "Audi", "Toyota", "Kia"),
        (18, 21, 16, 34, 19),
    ),
    (
        "closed",
        "Когда обычно переобуваетесь на зиму?",
        120,
        -(5 * 86400 + 120),
        (
            "Как только плюс семь",
            "Около плюс пяти",
            "По первому снегу",
            "Когда уже скользко",
            "Езжу на всесезонке",
        ),
        (29, 24, 27, 12, 6),
    ),
    (
        "closed",
        "Какой мотор брали чаще всего?",
        90,
        -(7 * 86400 + 90),
        (
            "1.6 атмосферный",
            "2.0 турбо",
            "1.5 турбо",
            "Дизель",
            "Гибрид",
            "Электро",
        ),
        (16, 24, 18, 7, 11, 5),
    ),
    (
        "closed",
        "Каско на новую машину — обязательно?",
        60,
        -(3 * 86400 + 60),
        ("Только ОСАГО", "ОСАГО и полное каско", "Мини-каско", "Пока без полиса"),
        (22, 36, 9, 2),
    ),
    (
        "closed",
        "Дилерский трейд-ин вас устраивает?",
        120,
        -(10 * 86400 + 120),
        (
            "Да, оценка честная",
            "Нет, сильно занижают",
            "Не сдавал машину",
            "Только при небольшой доплате",
        ),
        (7, 33, 12, 8),
    ),
    (
        "closed",
        "Какой кузов приятнее в дальней дороге?",
        180,
        -(26 * 3600 + 180),
        ("Седан", "Универсал", "Купе", "Лифтбек", "Кроссовер"),
        (19, 8, 13, 11, 15),
    ),
    (
        "closed",
        "Сколько мест нужно каждый день?",
        60,
        -(12 * 86400 + 60),
        ("Два", "Четыре", "Пять", "Семь"),
        (4, 11, 49, 17),
    ),
    (
        "closed",
        "Какая коробка меньше утомляет в пробке?",
        150,
        -(30 * 3600 + 150),
        ("Гидроавтомат", "Вариатор", "Робот с двумя сцеплениями", "Механика"),
        (38, 11, 8, 14),
    ),
    (
        "closed",
        "Какие фары реально светят ночью?",
        90,
        -(8 * 86400 + 90),
        ("Галоген", "Ксенон", "Обычный LED", "Матричный LED", "Лазер"),
        (6, 10, 27, 13, 0),
    ),
    (
        "closed",
        "Где обычно моете машину?",
        60,
        -(4 * 86400 + 60),
        (
            "Мойка самообслуживания",
            "Ручная мойка",
            "Робот",
            "Сам у дома",
            "Почти не мою",
        ),
        (19, 7, 12, 9, 2),
    ),
    (
        "closed",
        "С каким пробегом б/у ещё не страшно брать?",
        120,
        -(6 * 86400 + 120),
        (
            "До 50 тыс. км",
            "50–100 тыс. км",
            "100–150 тыс. км",
            "150–200 тыс. км",
            "Больше 200, если есть сервис",
        ),
        (28, 41, 19, 8, 5),
    ),
    (
        "closed",
        "Нужен ли третий ряд сидений?",
        90,
        -(15 * 86400 + 90),
        (
            "Да, для детей",
            "Иногда, в поездках",
            "Нет, не нужен",
            "Он съедает багажник",
        ),
        (13, 10, 18, 6),
    ),
    (
        "closed",
        "Какой привод честнее на укатанном снегу?",
        180,
        -(21 * 86400 + 180),
        (
            "Передний и хорошие шипы",
            "Полный",
            "Задний",
            "Главное — резина, не привод",
        ),
        (17, 39, 4, 11),
    ),
    (
        "closed",
        "Чем пользуетесь за рулём: CarPlay или штатной навигацией?",
        60,
        -(9 * 86400 + 60),
        (
            "Apple CarPlay",
            "Android Auto",
            "Штатная навигация",
            "Телефон в держателе",
        ),
        (34, 21, 13, 11),
    ),
    (
        "closed",
        "Какие зимние шины ставите на свою машину?",
        120,
        -(14 * 86400 + 120),
        (
            "Nokian",
            "Michelin",
            "Continental",
            "Pirelli",
            "Yokohama",
            "Cordiant",
            "Кама",
            "Что есть в моём размере",
        ),
        (17, 13, 15, 7, 6, 11, 5, 9),
    ),
    (
        "closed",
        "Когда пересели бы на электромобиль?",
        180,
        -(30 * 86400 + 180),
        (
            "Уже езжу",
            "В ближайший год",
            "Через 3–5 лет",
            "Не планирую",
            "Возьму гибрид как компромисс",
        ),
        (12, 15, 34, 29, 18),
    ),
    (
        "closed",
        "Что проверяете перед дальней дорогой?",
        120,
        -(40 * 60 + 120),
        (
            "Давление и запаску",
            "Масло и антифриз",
            "Щётки и омывайку",
            "Прохожу весь чеклист",
            "Ничего, машина сама напомнит",
        ),
        (9, 6, 5, 16, 1),
    ),
    (
        "closed",
        "Откуда должна быть машина мечты?",
        90,
        -(18 * 86400 + 90),
        (
            "Германия",
            "Япония",
            "Корея",
            "Китай",
            "Франция",
            "США",
            "Италия",
            "Чехия",
            "Швеция",
            "Россия",
        ),
        (22, 27, 18, 14, 4, 6, 5, 8, 7, 9),
    ),
    (
        "cancelled",
        "Какой концепт ждёте к ближайшему автосалону?",
        180,
        2 * 86400,
        (
            "Городской электрохэтч",
            "Большой кроссовер",
            "Спортивное купе",
            "Возрождение универсала",
        ),
        None,
    ),
    (
        "cancelled",
        "Ночной эфир: механика против автомата",
        90,
        6 * 3600,
        ("Механика", "Автомат", "Зависит от машины"),
        None,
    ),
    (
        "cancelled",
        "Какой цвет кузова должен стать цветом года?",
        60,
        86400,
        (
            "Белый перламутр",
            "Глубокий чёрный",
            "Серо-зелёный",
            "Синий металлик",
            "Медный",
            "Жёлтый",
        ),
        None,
    ),
    (
        "cancelled",
        "Для дачи — пикап или рамный внедорожник?",
        120,
        3 * 3600,
        (
            "Пикап",
            "Рамный внедорожник",
            "Обычный кроссовер справится",
            "Ни то ни другое",
        ),
        None,
    ),
    (
        "cancelled",
        "Бензин или дизель для большого универсала?",
        3600,
        -15 * 60,
        ("Бензин", "Дизель"),
        (46, 19),
    ),
    (
        "cancelled",
        "Какая мощность вам действительно нужна?",
        3600,
        -25 * 60,
        ("До 150 л.с.", "150–200 л.с.", "200–300 л.с.", "Больше 300 л.с."),
        (14, 28, 17, 5),
    ),
    (
        "cancelled",
        "Когда покупаете зимний комплект?",
        120,
        -3 * 3600,
        (
            "Ещё в сентябре",
            "Когда падает температура",
            "Не покупаю, езжу на всесезонке",
        ),
        (22, 13, 4),
    ),
    (
        "cancelled",
        "Как понимаете, что масло пора менять?",
        180,
        -90 * 60,
        (
            "По моточасам",
            "По пробегу",
            "Раз в год, даже если мало ездил",
            "Как скажет мастер",
        ),
        (9, 21, 6, 12),
    ),
)


class ApiClient:
    def __init__(self, base_url: str, admin_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        }

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        data = json.dumps(body, ensure_ascii=False).encode() if body else None
        request_headers = headers or self.admin_headers
        last_error: Exception | None = None
        for attempt in range(4):
            request = urllib.request.Request(
                self.base_url + path,
                data=data,
                method=method,
                headers=request_headers,
            )
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = response.read()
                return json.loads(payload) if payload else None
            except urllib.error.HTTPError as exc:
                details = exc.read().decode()
                if exc.code >= 500 and attempt < 3:
                    time.sleep(0.25 * (attempt + 1))
                    last_error = exc
                    continue
                raise RuntimeError(f"{method} {path}: HTTP {exc.code}: {details}") from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise RuntimeError(f"{method} {path}: {exc}") from exc
        raise RuntimeError(f"{method} {path} failed: {last_error}")


def _options(labels: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
    return [
        {"key": f"option-{index + 1}", "label": label}
        for index, label in enumerate(labels)
    ]


def _payload(
    name: str,
    status: str,
    show_time: datetime | None,
    duration: int,
    labels: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "show_time": show_time.isoformat() if show_time else None,
        "duration_seconds": duration,
        "options": _options(labels),
    }


class DemoPoll:
    def __init__(
        self,
        *,
        phase: str,
        create: dict[str, Any],
        finalize: dict[str, Any] | None,
        votes: tuple[int, ...] | None,
    ) -> None:
        self.phase = phase
        self.create = create
        self.finalize = finalize
        self.votes = votes

    @property
    def name(self) -> str:
        return str(self.create["name"])


def demo_polls(now: datetime) -> list[DemoPoll]:
    polls: list[DemoPoll] = []
    opening = now - timedelta(seconds=20)
    for phase, name, duration, show_offset, labels, votes in CATALOG:
        show_time = None if show_offset is None else now + timedelta(seconds=show_offset)
        final_status = "published" if phase in {"scheduled", "live", "closed"} else phase
        final = _payload(name, final_status, show_time, duration, labels)
        if votes and phase in {"closed", "cancelled"}:
            create = _payload(name, "published", opening, 3600, labels)
            finalize: dict[str, Any] | None = final
        elif phase == "cancelled":
            create = _payload(name, "published", show_time, duration, labels)
            finalize = final
        else:
            create = final
            finalize = None
        polls.append(DemoPoll(phase=phase, create=create, finalize=finalize, votes=votes))
    _validate(polls, now)
    return polls


def _validate(polls: list[DemoPoll], now: datetime) -> None:
    if len(polls) < 50:
        raise RuntimeError(f"demo catalog has {len(polls)} polls, need at least 50")

    names = [poll.name for poll in polls]
    if len(names) != len(set(names)):
        raise RuntimeError("demo poll names must be unique")

    phases = {poll.phase for poll in polls}
    missing = {"draft", "scheduled", "live", "closed", "cancelled"} - phases
    if missing:
        raise RuntimeError(f"demo catalog misses phases: {sorted(missing)}")

    option_sizes = {len(poll.create["options"]) for poll in polls}
    for size in (2, 3, 4, 5, 6, 7, 8, 10):
        if size not in option_sizes:
            raise RuntimeError(f"demo catalog has no poll with {size} options")

    durations = {
        int((poll.finalize or poll.create)["duration_seconds"]) for poll in polls
    }
    if not any(duration < 60 for duration in durations) or 3600 not in durations:
        raise RuntimeError("demo durations should include both a short blitz and a full hour")

    saw_empty_option = False
    for poll in polls:
        stored = poll.finalize or poll.create
        labels = [option["label"] for option in stored["options"]]
        if len(labels) != len(set(labels)):
            raise RuntimeError(f"duplicate options in {poll.name}")
        if poll.votes is None:
            if poll.phase in {"live", "closed"}:
                raise RuntimeError(f"{poll.phase} poll has no votes: {poll.name}")
            continue
        if len(poll.votes) != len(labels) or sum(poll.votes) <= 0:
            raise RuntimeError(f"bad vote weights for {poll.name}")
        saw_empty_option = saw_empty_option or any(count == 0 for count in poll.votes)
        _validate_window(poll, now)

    if not saw_empty_option:
        raise RuntimeError("at least one option should have zero votes")


def _validate_window(poll: DemoPoll, now: datetime) -> None:
    stored = poll.finalize or poll.create
    if poll.phase == "draft":
        return
    show_time = datetime.fromisoformat(stored["show_time"])
    closes_at = show_time + timedelta(seconds=int(stored["duration_seconds"]))
    if poll.phase == "live" and closes_at < now + timedelta(minutes=12):
        raise RuntimeError(f"live poll closes too soon: {poll.name}")
    if poll.phase == "scheduled" and show_time <= now:
        raise RuntimeError(f"scheduled poll is not in the future: {poll.name}")
    if poll.phase == "closed" and closes_at > now - timedelta(minutes=5):
        raise RuntimeError(f"closed poll is still inside the voting window: {poll.name}")


def _cast_vote(api: ApiClient, question_id: int, option_key: str) -> None:
    api.request(
        f"/questionnaire/{question_id}/votes",
        method="POST",
        body={"option": option_key},
        headers={
            "Content-Type": "application/json",
            "Cookie": f"vid={uuid.uuid4()}",
        },
    )


def seed(api: ApiClient) -> None:
    now = datetime.now(UTC)
    existing = {question["name"] for question in api.request("/questions")}
    created: list[tuple[dict[str, Any], DemoPoll]] = []

    for poll in demo_polls(now):
        if poll.name in existing:
            continue
        created.append((api.request("/questions", method="POST", body=poll.create), poll))

    vote_jobs: list[tuple[int, str]] = []
    for question, poll in created:
        if not poll.votes:
            continue
        keys = [option["key"] for option in question["options"]]
        for option_key, count in zip(keys, poll.votes, strict=True):
            vote_jobs.extend((question["id"], option_key) for _ in range(count))

    if vote_jobs:
        print(f"Casting {len(vote_jobs)} votes...")
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [
                pool.submit(_cast_vote, api, question_id, option_key)
                for question_id, option_key in vote_jobs
            ]
            finished = 0
            for future in as_completed(futures):
                future.result()
                finished += 1
                if finished % 400 == 0 or finished == len(vote_jobs):
                    print(f"  {finished}/{len(vote_jobs)}")

    for question, poll in created:
        if poll.finalize is None:
            continue
        api.request(f"/questions/{question['id']}", method="PUT", body=poll.finalize)

    questions = api.request("/questions")
    counts: dict[str, int] = {}
    for question in questions:
        status = question["effective_status"]
        counts[status] = counts.get(status, 0) + 1
    summary = ", ".join(
        f"{status} {counts.get(status, 0)}"
        for status in ("live", "scheduled", "closed", "draft", "cancelled")
    )
    print(f"Created {len(created)} demo polls; total questions: {len(questions)}; {summary}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:8080")
    parser.add_argument("--admin-token", default="dev-admin-token")
    args = parser.parse_args()
    seed(ApiClient(args.api_url, args.admin_token))


if __name__ == "__main__":
    main()
