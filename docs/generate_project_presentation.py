from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


OUT = Path(__file__).with_name("09-project-presentation.pptx")

NAVY = "0B1020"
PANEL = "151C31"
PANEL_2 = "1D2742"
WHITE = "F5F7FF"
MUTED = "A8B2CB"
CYAN = "39D8FF"
PURPLE = "8B7CFF"
GREEN = "5DE2A5"
AMBER = "FFC857"
GRID = "2B3656"
FONT = "Aptos"
FONT_DISPLAY = "Aptos Display"


def rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value)


def rect(slide, x, y, w, h, fill=PANEL, line_color=None, radius=True):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(
        shape_type, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    shape.line.color.rgb = rgb(line_color or fill)
    shape.line.width = Pt(1.2)
    if radius:
        shape.adjustments[0] = 0.08
    return shape


def circle(slide, x, y, d, fill, line_color=None):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    shape.line.color.rgb = rgb(line_color or fill)
    return shape


def text(
    slide,
    value,
    x,
    y,
    w,
    h,
    size=20,
    color=WHITE,
    bold=False,
    align=PP_ALIGN.LEFT,
    valign=MSO_ANCHOR.TOP,
    font=FONT,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Pt(0)
    frame.margin_top = frame.margin_bottom = Pt(0)
    frame.vertical_anchor = valign
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = value
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = rgb(color)
    return box


def line(slide, x1, y1, x2, y2, color=GRID, width=2, arrow=False):
    connector = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Inches(x1),
        Inches(y1),
        Inches(x2),
        Inches(y2),
    )
    connector.line.color.rgb = rgb(color)
    connector.line.width = Pt(width)
    if arrow:
        connector.line.end_arrowhead = True
    return connector


def pill(slide, label, x, y, w, color=CYAN):
    rect(slide, x, y, w, 0.35, PANEL_2)
    text(
        slide,
        label.upper(),
        x,
        y + 0.07,
        w,
        0.18,
        10,
        color,
        True,
        PP_ALIGN.CENTER,
    )


def base_slide(prs, title, section, number):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = rgb(NAVY)
    pill(slide, section, 0.68, 0.4, 1.65)
    text(slide, title, 0.68, 0.9, 11.6, 0.62, 28, WHITE, True, font=FONT_DISPLAY)
    line(slide, 0.68, 1.61, 12.65, 1.61, GRID, 1)
    text(slide, f"{number:02d}", 12.17, 7.03, 0.48, 0.2, 10, MUTED, True)
    return slide


def numbered_item(slide, number, title, body, x, y, accent=CYAN):
    circle(slide, x, y, 0.46, accent)
    text(
        slide,
        str(number),
        x,
        y + 0.1,
        0.46,
        0.22,
        14,
        NAVY,
        True,
        PP_ALIGN.CENTER,
    )
    text(slide, title, x + 0.67, y - 0.01, 3.9, 0.3, 17, WHITE, True)
    text(slide, body, x + 0.67, y + 0.39, 4.05, 0.5, 13, MUTED)


def add_title_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = rgb(NAVY)

    pill(slide, "Работающий MVP", 0.78, 0.68, 1.85)
    text(
        slide,
        "Сервис\nТВ-опросов",
        0.78,
        1.43,
        6.6,
        1.72,
        45,
        WHITE,
        True,
        font=FONT_DISPLAY,
    )
    text(
        slide,
        "Зритель голосует по QR-коду.\nАдминистратор сразу видит результат.",
        0.8,
        3.48,
        6.65,
        0.92,
        20,
        MUTED,
    )
    rect(slide, 0.8, 5.42, 6.25, 0.78, PANEL, GRID)
    text(
        slide,
        "Просто для зрителя. Быстро для сервиса.",
        1.08,
        5.68,
        5.7,
        0.28,
        16,
        CYAN,
        True,
    )

    circle(slide, 8.64, 1.75, 3.25, PANEL_2, CYAN)
    text(
        slide,
        "100 млн",
        8.64,
        2.72,
        3.25,
        0.48,
        29,
        WHITE,
        True,
        PP_ALIGN.CENTER,
    )
    text(
        slide,
        "возможных зрителей",
        8.64,
        3.32,
        3.25,
        0.26,
        13,
        MUTED,
        align=PP_ALIGN.CENTER,
    )
    text(slide, "FASTAPI · REDIS · POSTGRESQL · REACT", 0.8, 6.86, 7.3, 0.2, 10, MUTED, True)


def add_product_slide(prs):
    slide = base_slide(prs, "Что умеет сервис", "Задача", 2)
    rect(slide, 0.73, 2.0, 5.72, 3.62, PANEL, GRID)
    rect(slide, 6.88, 2.0, 5.72, 3.62, PANEL, GRID)
    pill(slide, "Зритель", 1.05, 2.32, 1.25, CYAN)
    pill(slide, "Администратор", 7.2, 2.32, 1.95, PURPLE)

    viewer = [
        "Открывает ссылку по QR-коду",
        "Голосует без регистрации",
        "Не может случайно проголосовать дважды",
    ]
    admin = [
        "Создаёт и запускает опрос",
        "Получает ссылку и QR-код",
        "Смотрит результаты в реальном времени",
    ]
    for items, x, accent in ((viewer, 1.06, CYAN), (admin, 7.21, PURPLE)):
        for index, value in enumerate(items, 1):
            y = 3.08 + (index - 1) * 0.76
            circle(slide, x, y + 0.04, 0.25, accent)
            text(slide, value, x + 0.47, y, 4.72, 0.46, 15, WHITE)

    rect(slide, 2.0, 6.08, 9.34, 0.66, PANEL_2)
    text(
        slide,
        "Главная сложность: много голосов приходит почти одновременно.",
        2.0,
        6.29,
        9.34,
        0.25,
        15,
        AMBER,
        True,
        PP_ALIGN.CENTER,
    )


def add_architecture_slide(prs):
    slide = base_slide(prs, "Как всё связано", "Схема", 3)
    nodes = [
        ("Зритель", "открывает QR", 0.78, CYAN),
        ("API", "проверяет запрос", 3.62, PURPLE),
        ("Redis", "быстро считает", 6.46, GREEN),
        ("PostgreSQL", "надёжно хранит", 9.3, AMBER),
    ]
    for index, (title, body, x, accent) in enumerate(nodes):
        rect(slide, x, 2.43, 2.28, 1.42, PANEL, accent)
        text(slide, title, x, 2.76, 2.28, 0.31, 18, WHITE, True, PP_ALIGN.CENTER)
        text(slide, body, x, 3.2, 2.28, 0.25, 12, MUTED, align=PP_ALIGN.CENTER)
        if index < len(nodes) - 1:
            line(slide, x + 2.28, 3.14, nodes[index + 1][2], 3.14, accent, 2.2, True)

    rect(slide, 1.08, 4.78, 11.16, 1.28, PANEL_2, GRID)
    text(slide, "Redis принимает пик", 1.47, 5.1, 3.15, 0.31, 17, GREEN, True)
    text(slide, "PostgreSQL сохраняет историю", 4.94, 5.1, 3.64, 0.31, 17, AMBER, True)
    text(slide, "API можно масштабировать", 8.83, 5.1, 2.94, 0.31, 17, CYAN, True)
    text(
        slide,
        "Быстрая часть и надёжная часть не мешают друг другу.",
        1.08,
        6.52,
        11.16,
        0.3,
        16,
        WHITE,
        True,
        PP_ALIGN.CENTER,
    )


def add_vote_slide(prs):
    slide = base_slide(prs, "Что происходит после нажатия", "Один голос", 4)
    numbered_item(slide, 1, "Проверяем опрос", "Он опубликован и ещё открыт.", 0.88, 2.14)
    numbered_item(slide, 2, "Проверяем ответ", "Такой вариант действительно существует.", 6.75, 2.14, PURPLE)
    numbered_item(slide, 3, "Проверяем повтор", "Этот браузер ещё не голосовал.", 0.88, 3.78, GREEN)
    numbered_item(slide, 4, "Сохраняем голос", "Счётчик обновляется сразу, журнал пишется следом.", 6.75, 3.78, AMBER)

    rect(slide, 1.55, 5.63, 10.22, 0.76, PANEL_2, GREEN)
    text(
        slide,
        "Проверка повтора и увеличение счётчика выполняются вместе.",
        1.55,
        5.88,
        10.22,
        0.28,
        16,
        WHITE,
        True,
        PP_ALIGN.CENTER,
    )
    text(
        slide,
        "Новый голос → принят   ·   повторный голос → отклонён",
        1.55,
        6.62,
        10.22,
        0.25,
        14,
        MUTED,
        align=PP_ALIGN.CENTER,
    )


def add_demo_slide(prs):
    slide = base_slide(prs, "Демонстрация проекта", "Демо", 5)
    rect(slide, 0.72, 1.96, 8.15, 4.78, PANEL, CYAN)
    circle(slide, 4.12, 3.38, 1.18, CYAN)
    text(
        slide,
        "▶",
        4.19,
        3.66,
        1.0,
        0.36,
        28,
        NAVY,
        True,
        PP_ALIGN.CENTER,
    )
    text(
        slide,
        "МЕСТО ДЛЯ ВИДЕО",
        1.74,
        4.9,
        6.12,
        0.32,
        17,
        WHITE,
        True,
        PP_ALIGN.CENTER,
    )
    text(
        slide,
        "Оптимальная длительность: 60–90 секунд",
        1.74,
        5.38,
        6.12,
        0.25,
        12,
        MUTED,
        align=PP_ALIGN.CENTER,
    )

    text(slide, "В видео", 9.38, 2.05, 2.4, 0.34, 19, WHITE, True)
    points = [
        "Создание опроса",
        "Голосование по QR",
        "Живой результат",
        "Защита от повтора",
    ]
    for index, value in enumerate(points, 1):
        y = 2.75 + (index - 1) * 0.83
        circle(slide, 9.38, y, 0.4, CYAN if index < 3 else GREEN)
        text(
            slide,
            str(index),
            9.38,
            y + 0.09,
            0.4,
            0.2,
            12,
            NAVY,
            True,
            PP_ALIGN.CENTER,
        )
        text(slide, value, 10.0, y + 0.04, 2.55, 0.32, 14, WHITE)


def add_summary_slide(prs):
    slide = base_slide(prs, "Итог", "Готово", 6)
    cards = [
        ("Рабочий продукт", "Публичная форма и админка", CYAN),
        ("Быстрый приём", "Redis считает голоса", GREEN),
        ("Надёжный итог", "PostgreSQL хранит историю", AMBER),
    ]
    for index, (title, body, accent) in enumerate(cards):
        x = 0.76 + index * 4.14
        rect(slide, x, 2.03, 3.72, 1.45, PANEL, accent)
        text(slide, title, x + 0.27, 2.38, 3.18, 0.3, 18, WHITE, True)
        text(slide, body, x + 0.27, 2.85, 3.18, 0.25, 12, MUTED)

    text(slide, "Что нужно для большой нагрузки", 0.78, 4.12, 4.5, 0.34, 20, WHITE, True)
    next_steps = [
        "Провести полноценный нагрузочный тест",
        "Добавить мониторинг и уведомления",
        "Сделать журнал устойчивым к падению процесса",
    ]
    for index, value in enumerate(next_steps, 1):
        y = 4.72 + (index - 1) * 0.56
        text(slide, f"{index:02d}", 0.8, y, 0.43, 0.22, 11, PURPLE, True)
        text(slide, value, 1.42, y - 0.02, 5.35, 0.28, 14, MUTED)

    rect(slide, 7.37, 4.1, 5.16, 2.08, PANEL_2, GREEN)
    text(
        slide,
        "Главный результат",
        7.7,
        4.48,
        4.5,
        0.3,
        14,
        GREEN,
        True,
        PP_ALIGN.CENTER,
    )
    text(
        slide,
        "Система уже работает\nи готова к демонстрации.",
        7.7,
        5.0,
        4.5,
        0.72,
        22,
        WHITE,
        True,
        PP_ALIGN.CENTER,
    )


def build():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = "Сервис ТВ-опросов"
    prs.core_properties.subject = "Краткая презентация проекта"
    prs.core_properties.author = "Crypto Enthusiast"

    add_title_slide(prs)
    add_product_slide(prs)
    add_architecture_slide(prs)
    add_vote_slide(prs)
    add_demo_slide(prs)
    add_summary_slide(prs)

    prs.save(OUT)
    print(f"Saved {len(prs.slides)} slides to {OUT}")


if __name__ == "__main__":
    build()
