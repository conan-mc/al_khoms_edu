# al_khoms_edu

تخصيصات **المعهد العالي للعلوم والتقنية — الخمس** كحزمة ERPNext قياسية.

## البنية (نهج ERPNext)

| المكوّن | المكان |
|--------|--------|
| الكود (المنطق) | `al_khoms_edu/*.py` — `regulations`, `seed`, `academic_engine`, `verification`, `print_helpers` |
| الأحداث (Events) | `al_khoms_edu/hooks.py` — `doc_events`, `scheduler_events`, `after_install`, `after_migrate`, `jinja` |
| الواجهة (UI) | `al_khoms_edu/fixtures/` — Custom Field, Property Setter, Print Format, Custom DocPerm |
| الأصول | `al_khoms_edu/public/` + `al_khoms_edu/templates/` |
| الترحيلات | `al_khoms_edu/patches/` + `al_khoms_edu/patches.txt` |

## المتطلبات

- `frappe` >= 16, < 17
- `erpnext` >= 16, < 17
- `education` >= 16, < 17
- `pos_next` >= 2, < 3

معلنة في `hooks.py` (`required_apps`) و`pyproject.toml` (`[tool.bench.frappe-dependencies]`).

## التثبيت

```bash
cd ~/frappe-bench

bench get-app erpnext   --branch version-16
bench get-app education --branch version-16
bench get-app pos_next  --branch develop

bench get-app al_khoms_edu https://github.com/conan-mc/al_khoms_edu.git --branch main
bench setup requirements

bench --site <site> install-app al_khoms_edu
bench --site <site> migrate
```

> **مهم:** `install-app` يعلّم كل patches التطبيق (ومنها `run_seed`) كمكتملة دون
> تنفيذها. بعد إنشاء **شركة** المعهد عبر معالج الإعداد، نفّذ التهيئة صراحةً:
>
> ```bash
> bench --site <site> execute al_khoms_edu.seed.run
> ```

## الاعتماديات

توليد QR لكشف الدرجات يعتمد على `PyQRCode` و`pypng` (معلنة في `pyproject.toml`).
تحقّق:

```bash
env/bin/python -c "import pyqrcode, png; print('QR deps OK')"
```

## التحقق

يُستخدم سكربت `verify_transfer.py` من مستودع التوثيق
(`conan-mc/al-khoms-edu` → `migration/phase2/`) من داخل `~/frappe-bench`:

```bash
env/bin/python verify_transfer.py <site>
# المتوقع: RESULT: PASS — Custom Field = 102
```

## الترخيص

MIT — انظر `license.txt`.
