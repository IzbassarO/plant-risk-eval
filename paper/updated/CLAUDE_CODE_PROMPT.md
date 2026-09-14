# Задание для Claude Code — ICA 2026, доводка пайплайна

Ты уже починил экранирование и разделители разрядов. Это продолжение.
В `paper/updated/` добавлены два файла:

- `ica26_verify_tables.py` — проверка таблиц после перегенерации
- `results_macros_additions.tex` — макросы, которых не хватает в репозитории

---

## ПОРЯДОК ВАЖЕН

Пункт 0 нужно сделать **до любой перегенерации таблиц**. После неё сделать
снимок будет уже не с чего.

---

## 0. Снимок значений — прямо сейчас, до всего остального

```bash
cp paper/updated/ica26_verify_tables.py scripts/
python scripts/ica26_verify_tables.py snapshot \
    --tables experiments/ica26/tables \
    --snapshot build/table_numbers.json
git add build/table_numbers.json && git commit -m "snapshot table values before regeneration"
```

Это фиксирует каждый числовой токен во всех 16 таблицах. Мы меняем форматирование —
ни одна цифра сдвинуться не должна. После любой правки генератора:

```bash
python scripts/ica26_verify_tables.py check --tables experiments/ica26/tables
```

---

## 1. КРИТИЧНО: проверь, что `cell()` конвертирует Unicode

Ты удалил из `ica26_significance.py`:

```python
for raw, tex in (("±", r"$\pm$"), ("→", r"$\rightarrow$"), ("->", r"$\rightarrow$")):
    latex = latex.replace(raw, tex)
```

**Этот цикл делал реальную работу.** DataFrame'ы держат `0.9945 ± 0.0021` с
Unicode-символом `±`, и `escape=True` в pandas `±` не трогает — именно цикл
превращал его в `$\pm$`. То же с `→` в метках вроде
`PlantVillage → PlantDoc Core`.

Удаление цикла корректно **только если `latexfmt.cell()` теперь несёт карту
Unicode → LaTeX**. Если не несёт, каждая таблица тихо получит сырой UTF-8, и
pdfLaTeX упадёт на `Unicode character ± not set up for use with LaTeX`.

Проверь `src/ica26/experiments/latexfmt.py`. Если карты нет — добавь в `cell()`
как минимум:

| символ | замена |
|---|---|
| `±` | `$\pm$` |
| `→` | `$\rightarrow$` |
| `≤` `≥` | `$\leq$` `$\geq$` |
| `×` | `$\times$` |
| `−` (U+2212) | `-` |
| `–` `—` | `--` `---` |

Порядок применения: сначала экранирование спецсимволов LaTeX, потом карта
Unicode. Иначе `$` из `$\pm$` сам получит экранирование.

`ica26_verify_tables.py check` ловит это — пункт `[2]` в его выводе.

---

## 2. Литералы заголовков должны стать обычным текстом

Заголовки теперь проходят через тот же гейт: экранируются, если не помечены
`Raw`. Значит источник заголовка обязан быть **голым текстом**, а не LaTeX.

Если где-то осталось `r"Rel. drop (\%)"`, новый гейт экранирует обратный слэш и
`\textbackslash \%` вернётся третий раз.

Пройди по всем строкам заголовков в `ica26_build_tables.py` и
`ica26_significance.py`:

- `"Rel. drop (%)"` — голый текст, гейт сам сделает `\%`
- `Raw(r"PV $\rightarrow$ PDC")` — намеренная разметка, помечена `Raw`
- `Raw(r"$\Delta$ acc.")` — то же

Правило: если строка должна попасть в PDF как символ — голый текст.
Если как разметка — `Raw`.

---

## 3. Регрессионный тест

Оба дефекта уже возвращались по одному разу. Нужен тест, а не только починка.
В `tests/test_table_generation.py`:

```python
import re
from pathlib import Path
import pytest

TABLES = Path("experiments/ica26/tables")

@pytest.mark.parametrize("path", sorted(TABLES.glob("*.tex")), ids=lambda p: p.name)
def test_no_double_escaping(path):
    src = path.read_text()
    assert r"\textbackslash" not in src
    assert not re.search(r"\\\$\\\\", src)

@pytest.mark.parametrize("path", sorted(TABLES.glob("*.tex")), ids=lambda p: p.name)
def test_no_unresolved_unicode(path):
    src = path.read_text()
    for ch in "±→≤≥×−–—":
        assert ch not in src, f"{ch!r} не сконвертирован в LaTeX"

def test_identifier_columns_not_separated():
    """seed 1337 именует прогон, а не считает — разделителя быть не должно."""
    src = (TABLES / "table7_ranking_stability.tex").read_text()
    assert r"1\,337" not in src and r"2\,026" not in src
```

Плюс юнит-тест на сам `latexfmt`:

```python
from ica26.experiments.latexfmt import Raw, cell, fmt_int

def test_raw_passes_through():
    assert cell(Raw(r"$\Delta$")) == r"$\Delta$"

def test_data_is_escaped():
    assert cell("50% drop") == r"50\% drop"

def test_bool_is_not_an_integer():
    assert "1" not in cell(True)          # isinstance(True, int) is True

def test_fmt_int_matches_macros():
    assert fmt_int(54305) == r"54\,305"
```

---

## 4. Ширина таблиц — мерить НАСТОЯЩИМ llncs.cls

Десять из шестнадцати таблиц шире текстового блока. Точные лимиты:

| документ | `\textwidth` |
|---|---|
| статья, `\documentclass[runningheads]{llncs}` | **347.1 pt = 122.0 мм** |
| приложение, `\usepackage[margin=15mm,a4paper]{geometry}` | **180 мм** |
| `sidewaystable` в приложении | **265 мм** (по высоте страницы) |

**Ключевой момент, на котором легко ошибиться:** мерить надо настоящим классом
документа. Замер в `article` занижает ширину, потому что `\multicolumn` с
`\cmidrule` растягивает колонки сверх содержимого. Я на этом сам ошибся:
`table6_calibration_compact` показала 117.8 мм в `article` при реальном
переполнении на 14 pt в `llncs`.

Замерочный харнесс:

```python
def measure_pt(tabular_src, size, tabcolsep):
    doc = (r"\documentclass[runningheads]{llncs}"
           r"\usepackage[T1]{fontenc}\usepackage{booktabs}\usepackage{amsmath,amssymb}"
           r"\newsavebox{\mb}\begin{document}"
           f"\\sbox{{\\mb}}{{{size}\\setlength{{\\tabcolsep}}{{{tabcolsep}pt}}{tabular_src}}}"
           r"\typeout{M::\the\wd\mb}\end{document}")
    # прогнать pdflatex во временной папке, вынуть M:: из лога
```

Перебор: `(footnotesize, scriptsize, tiny) × (6, 5, 4, 3, 2) pt`, брать первую
пару, укладывающуюся в `\textwidth - 3pt`. Если ничего не влезло и таблица идёт
в приложение — заворачивать в `sidewaystable` и убедиться, что в
`supplementary.tex` есть `\usepackage{rotating}`.

**Чего не делать:** менять значения ради ширины. Сокращать можно только имена
моделей в теле таблицы (`MobileNetV3-Small` → `MobileNetV3-S`) и только если в
подписи есть расшифровка. Имена бэкбонов в первом столбце оставить полностью —
читатель именно их сравнивает.

---

## 5. Компактные варианты table6 и table9 — НЕ перезаписывать старой формой

Это самое важное для сдачи. Статья доведена до **15 страниц при лимите 12–15**,
и две страницы из семнадцати сэкономлены именно транспонированием этих двух
таблиц. Если генератор выдаст их в прежней форме, статья вернётся к 17 страницам
и выйдет за лимит.

Требуемая форма:

**`table6_calibration_compact.tex`** — было 18 строк, надо 3.
Строки = бэкбоны. Колонки = четыре режима PlantVillage-обученной модели:

```
                & PlantVillage test        & PlantDoc Core (shift)
Model           & uncalibrated & with T    & uncalibrated & with T
ResNet-50       & ECE          & ECE       & ECE          & ECE
EfficientNet-B0 & ...
MobileNetV3-S   & ...
```

Столбцы PlantDoc-обученной калибровки в компактный вариант **не идут** — в
основном тексте они не обсуждаются, только в приложении. Температуры в
компактном варианте тоже не нужны: они процитированы в прозе через макросы.
Подобранный формат: `\footnotesize`, `tabcolsep 2pt`, ширина 341.1 pt.

**`table9_significance_across_seeds_compact.tex`** — было 9 строк, надо 3.
Строки = три постановки оценки. Колонки = три пары бэкбонов, по три подколонки
на пару:

```
              & \multicolumn{3}{c}{RN50 vs EB0} & \multicolumn{3}{c}{RN50 vs MNv3-S} & \multicolumn{3}{c}{EB0 vs MNv3-S}
Evaluation    & sig & sgn & $\Delta$ | sig & sgn & $\Delta$ | sig & sgn & $\Delta$
PlantVillage (lab)     & 1/3 & no  & -0.0019 & ...
PlantDoc Core (field)  & 0/3 & no  & -0.0015 & ...
PV → PDC (shift)       & 0/3 & no  & -0.0070 & ...
```

Подобранный формат: `\scriptsize`, `tabcolsep 4pt`, ширина 307.6 pt.

Полные версии (`table6_calibration.tex`, `table9_significance_across_seeds.tex`)
остаются как есть — они идут в приложение.

Ещё две компактные таблицы, которые статья использует, подобраны так:
`table2_in_domain_performance_compact` — `footnotesize`, 6pt, 320.8 pt;
`table3_cross_domain_performance_compact` — `footnotesize`, 5pt, 342.1 pt
(этот на грани, 342 из 347 — без замера настоящим классом уехал бы в поле).

`table1_dataset_statistics.tex` статья больше не подключает: его числа дословно
повторены в прозе §3.1. Генерировать можно, в статью не вставлять.

---

## 6. Preflight в build-скрипт

```bash
cp paper/updated/ica26_preflight.py scripts/
```

и в `scripts/ica26_build_paper.sh` перед первым вызовом `pdflatex`:

```bash
python scripts/ica26_preflight.py --root paper --entry ica2026.tex || exit 1
```

Напоминание, зачем: одна отсутствующая таблица уронила сборку с `Emergency stop`,
после чего каждая цитата и ссылка стали `[?]` и `??`, а PDF молча обрезался на 8
странице из 17. Симптом выглядел как проблема с библиографией, а был отсутствующий
`\input`.

---

## 7. Два `[PENDING]` макроса

`results_macros_additions.tex` — временный мост. Двенадцать макросов, из них
десять уже несут вычисленные значения, а два помечены `\ResultPending` и
печатаются в PDF как `[PENDING]`.

Заполнить надо `\AccXdMajority` и `\MacroFXdMajority` — тривиальный бейзлайн на
cross-domain наборе. Обучать ничего не нужно, только замороженный манифест:

```python
y = labels_of(xd_manifest)              # 1951 изображение, 21 общий класс
maj = Counter(y).most_common(1)[0][0]
acc = (y == maj).mean()
f1  = f1_score(y, np.full_like(y, maj), average="macro", labels=present_classes)
```

Берём предиктор «всегда самый частый класс», а не равномерно случайный: при
перекошенном распределении он строже и потому честнее как нижняя граница.

Дальше сложить все двенадцать в `ica26_build_paper_macros.py` и удалить
`results_macros_additions.tex` вместе с его `\input` из `ica2026.tex`.

Остальные десять уже посчитаны из значений в `results_macros.tex` арифметикой,
но их всё равно должен эмитить генератор, а не хардкод:

- `\EceRatioRn/Eb/Mn` = `mean_ece[m]["xd_T"] / mean_ece[m]["xd"]`
- `\TempSdMax` = `max(sd_of_fitted_T[m] for m in backbones)` по PlantVillage
- `\MacroFPvInShared*`, `\RelDropFShared*` — см. пункт 8

---

## 8. Опционально, но это то, о чём спросит рецензент

**21-классный in-domain контроль.** Прямой ответ на первое ограничение статьи
(«две разметки различаются, падение смешивает сдвиг домена с изменением сложности
задачи»). Переобучать ничего не надо: взять **сохранённые логиты
PlantVillage-теста**, применить ту же суммацию по каноническим классам и
ренормализацию, что и в cross-domain, и посчитать метрики только на тех тестовых
изображениях, чей класс попал в общее пространство. Получается 21-way → 21-way,
то есть чистый сдвиг домена при фиксированной сложности. Макросы под это уже
зарезервированы: `\MacroFPvInShared*`, `\RelDropFShared*`.

**Ablation без label smoothing.** Один прогон, один бэкбон, один сид. Сейчас
вывод про калибровку честно ограничен связкой «label smoothing + in-domain
температура», и это записано в Limitations. Один прогон либо снимет ограничение,
либо подтвердит его.

---

## Критерии приёмки

```bash
python scripts/ica26_verify_tables.py check --tables experiments/ica26/tables
pytest tests/test_table_generation.py -q
bash scripts/ica26_build_paper.sh
```

Должно выполняться всё:

- [ ] `verify_tables check` — ноль проблем по всем четырём пунктам, включая `[4]`
      «значения не сдвинулись»
- [ ] ни одного `\textbackslash` и ни одного голого `±` `→` `≤` `×` в
      `experiments/ica26/tables/*.tex`
- [ ] в `table7_ranking_stability.tex` seed'ы записаны `1337` и `2026`,
      без `\,`
- [ ] `54\,305`, `43\,596`, `1\,951` — одинаково и в таблицах, и в
      `results_macros.tex`
- [ ] `ica2026.pdf` — **ровно 15 страниц**, `pdflatex` (не XeLaTeX)
- [ ] в логе ноль `! `, ноль `undefined`, ноль `Overfull \hbox` больше 5 pt
- [ ] `pdftotext ica2026.pdf - | grep -c PENDING` даёт `0`
- [ ] `supplementary.pdf` собирается, ни одна таблица не выходит за поля
- [ ] preflight стоит в build-скрипте и падает, если убрать любой `\input`

Если после перегенерации `verify_tables` покажет `[4] ЗНАЧЕНИЯ ИЗМЕНИЛИСЬ` —
останавливайся и разбирайся, прежде чем что-либо коммитить. Мы правим
форматирование; сдвиг цифры означает, что задет не тот слой.
