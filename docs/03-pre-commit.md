# 3. Контроль якості коду: ruff + pre-commit

## Що налаштовано

- **ruff** (`pyproject.toml`) — лінтер і форматер. Замінює одразу flake8,
  isort і black, але працює в десятки разів швидше.
- **pre-commit** (`.pre-commit-config.yaml`) — запускає перевірки
  автоматично перед кожним `git commit`. Якщо хоча б одна перевірка не
  пройшла, **коміт не створюється**.

| Хук | Що перевіряє |
|---|---|
| `check-ast` | Python-файл взагалі можна розібрати (немає синтаксичних помилок) |
| `trailing-whitespace`, `end-of-file-fixer` | зайві пробіли, порожній рядок у кінці файлу |
| `check-yaml` | синтаксис YAML (docker-compose, конфіг pre-commit) |
| `check-added-large-files`, `detect-private-key` | випадково доданий великий файл або секретний ключ |
| `ruff` | помилки та стиль: невикористані імпорти, неіснуючі змінні, PEP 8 |
| `ruff-format` | однакове форматування коду (відступи, пробіли, лапки) |

## Як відтворити демонстрацію

```bash
pre-commit install          # один раз після клонування репозиторію
```

### Демо 1: синтаксична помилка → коміт заблоковано

```bash
printf 'def broken(:\n    return 1\n' > app/bad_syntax.py
git add app/bad_syntax.py
git commit -m "try broken code"
```

Результат:
```
check python ast.........................................................Failed
    SyntaxError: invalid syntax
ruff.....................................................................Failed
app/bad_syntax.py:1:12: SyntaxError: Expected a parameter or the end of the parameter list
ruff-format..............................................................Failed
```
`git log` показує, що нового коміту немає.

### Демо 2: неохайний код → заблоковано, хуки виправили самі

```python
import os
import sys

def add( a,b ):
    x=a+b
    return x
```
```
ruff.....................................................................Failed
- files were modified by this hook
Found 2 errors (2 fixed, 0 remaining).
ruff-format..............................................................Failed
- files were modified by this hook
```
Хуки прибрали невикористані імпорти й відформатували файл, але коміт
**все одно заблоковано**: розробник має переглянути зміни, ще раз
виконати `git add` і `git commit`.

### Демо 3: помилка, яку не можна виправити автоматично

```python
def total(price):
    return price * quantity
```
```
ruff.....................................................................Failed
app/bad_name.py:2:20: F821 Undefined name `quantity`
```
Тут ruff лише показує проблему, виправити її має людина.

### Прибирання після демонстрації

```bash
git restore --staged app/bad_*.py
rm app/bad_*.py
```
