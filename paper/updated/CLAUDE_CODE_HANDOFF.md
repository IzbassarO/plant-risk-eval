# Для Claude Code: что чинить в генераторе

Ты был прав, что это место для правок, а не Overleaf. Ниже три дефекта в
`scripts/ica26_build_tables.py`, каждый из которых уже проявился в собранном PDF.
Правь генератор — вывод перезатрётся при следующем запуске.

---

## 1. Двойное экранирование LaTeX (проявился дважды, будет третий раз)

Генератор экранирует LaTeX, который должен остаться LaTeX'ом. В PDF печатается
буквальный текст вместо символа.

**Где уже видно:**

| файл | в файле | в PDF |
|---|---|---|
| `table5_domain_shift_degradation_compact.tex` | `Rel. drop (\textbackslash \%)` | `Rel. drop (\%)` |
| `table9_significance_across_seeds_compact.tex` | `PV \$\textbackslash rightarrow\$ PDC` | `PV $\rightarrow$ PDC` |
| то же | `\$\textbackslash Delta\$ acc.` | `$\Delta$ acc.` |

**Причина:** экранирующая функция применяется к строкам, которые уже содержат
намеренную LaTeX-разметку. Скорее всего что-то вроде
`latex_escape(f"PV $\\rightarrow$ PDC")`.

**Как чинить:** разделить два потока. Значения из CSV/JSON экранируются;
заголовки, подписи и метки, которые ты пишешь сам, не экранируются никогда.
Практично — обернуть намеренную разметку в тип-маркер:

```python
class Raw(str):
    """LaTeX, который нельзя экранировать."""

def cell(v):
    return v if isinstance(v, Raw) else latex_escape(str(v))

SETTING_LABELS = {
    "xd": Raw(r"PV $\rightarrow$ PDC"),
    "pv_in": "PlantVillage in-domain",
}
```

**Тест-регрессия, чтобы не вернулось:**

```python
def test_no_double_escaping():
    for path in TABLE_DIR.glob("*.tex"):
        src = path.read_text()
        assert r"\textbackslash" not in src, f"{path.name}: двойное экранирование"
        assert r"\$" not in src.replace(r"\\$", ""), f"{path.name}: экранированный $"
```

---

## 2. Разделители разрядов расходятся с макросами

`generated/results_macros.tex` пишет `54\,305`, `1\,951`, `10\,000`.
`tables/*.tex` пишет `54305`, `1951`, `10000`.

Одна и та же величина в одном документе выглядит двумя способами: в §3.1 текст
даёт `54 305`, а таблица рядом `54305`.

**Как чинить:** одна функция форматирования целых на оба генератора.

```python
def fmt_int(n: int) -> str:
    """Тонкий пробел как разделитель тысяч, как в results_macros."""
    return f"{n:,}".replace(",", r"\,")
```

Вызывать её и в `ica26_build_paper_macros.py`, и в `ica26_build_tables.py`.

---

## 3. Ширина таблиц не проверяется

Десять из шестнадцати сгенерированных таблиц шире текстового блока. Настоящие
цифры (замерено компиляцией с настоящим `llncs.cls`, `\textwidth` = 347.1 pt =
122 мм; в приложении с `margin=15mm` это 180 мм):

| таблица | ширина | лимит | переполнение |
|---|---|---|---|
| table5_domain_shift_degradation | 353 мм | 180 | +173 |
| table3_cross_domain_performance | 345 мм | 180 | +165 |
| table7_ranking_stability | 321 мм | 180 | +141 |
| table6_calibration | 288 мм | 180 | +108 |
| table4_efficiency | 266 мм | 180 | +86 |
| table2_in_domain_performance | 260 мм | 180 | +80 |
| table8b_mcnemar | 249 мм | 180 | +69 |
| table7b_ranking_margins | 245 мм | 180 | +65 |
| table9_significance_across_seeds | 215 мм | 180 | +35 |
| table8_confidence_intervals | 200 мм | 180 | +20 |

Три не влезают даже в `\tiny` — им нужен `sidewaystable` и `\usepackage{rotating}`
в преамбуле приложения.

**Как чинить:** после записи каждой таблицы измерить её настоящей компиляцией и
подобрать минимальный кегль и `tabcolsep`, которые влезают. Ключевой момент,
на котором я сам сначала ошибся: измерять надо **настоящим классом документа**.
Замер в `article` занижает ширину, потому что `\multicolumn` с `\cmidrule`
растягивает колонки сверх содержимого — у меня из-за этого table6 показалась
117.8 мм при реальном переполнении на 14 pt.

```python
def measure_pt(tabular_src, size, tabcolsep, cls="llncs"):
    doc = (f"\\documentclass[runningheads]{{{cls}}}"
           r"\usepackage[T1]{fontenc}\usepackage{booktabs}\usepackage{amsmath,amssymb}"
           r"\newsavebox{\mb}\begin{document}"
           f"\\sbox{{\\mb}}{{{size}\\setlength{{\\tabcolsep}}{{{tabcolsep}pt}}{tabular_src}}}"
           r"\typeout{M::\the\wd\mb}\end{document}")
    # ... прогнать pdflatex, вынуть M:: из лога
```

Перебирать `(footnotesize, scriptsize, tiny) × (6,5,4,3,2)pt`, брать первую
пару, укладывающуюся в `\textwidth - 3pt`. Если ни одна не влезла и таблица идёт
в приложение — заворачивать в `sidewaystable`.

**Чего не делать:** менять значения ради ширины. Сокращать можно только имена
моделей в теле таблицы (`MobileNetV3-Small` → `MNv3-S`) и только если в подписи
дана расшифровка.

---

## 4. Preflight в build-скрипт

Одна отсутствующая таблица уронила всю сборку с `Emergency stop`, после чего
каждая цитата и ссылка в документе стали `[?]` и `??`, а PDF молча обрезался на
8 странице из 17. Симптом выглядел как проблема с библиографией.

Одна строка в `ica26_build_paper.sh` перед вызовом `pdflatex`:

```bash
python scripts/ica26_preflight.py --root paper || exit 1
```

Скрипт рекурсивно проверяет `\input`, `\includegraphics`, `\bibliography`,
`\bibliographystyle` и `\ref` без `\label`.

---

## Что ещё осталось открытым в самой статье

1. **Два `[PENDING]`** — majority-baseline на cross-domain наборе. Пять строк
   кода по замороженному манифесту, обучать ничего не надо:

   ```python
   y = labels_of(xd_manifest)            # 1951 картинка, 21 класс
   maj = Counter(y).most_common(1)[0][0]
   acc = (y == maj).mean()
   f1  = f1_score(y, np.full_like(y, maj), average="macro", labels=present)
   ```

   Без этого числа читатель не может сказать, 0.26 на 21 классе — это много или
   мало.

2. **21-классный in-domain контроль** — прямой ответ на Limitation 1, тоже без
   переобучения: взять сохранённые логиты PlantVillage-теста, применить ту же
   суммацию по каноническим классам и ренормализацию, посчитать только на тех
   тестовых картинках, чей класс попал в shared space. Получается 21-way → 21-way,
   то есть чистый сдвиг домена при фиксированной сложности задачи.

3. **Ablation без label smoothing** — один прогон, один бэкбон, один сид.
   Сейчас вывод про калибровку ограничен связкой «label smoothing + in-domain
   температура», и это честно записано в Limitations. Один прогон снимет
   ограничение или подтвердит его.

4. **Ссылка на прошлые труды ICA** — в `references.bib` нет ни одной работы из
   ICA 2023/2024/2025 CCIS. Для четвёртого издания конференции это заметно.
