# -*- coding: utf-8 -*-
"""verification.py — توقيع الوثائق الرسمية ورمز QR ورابط التحقق العام.

الغرض: تمكين أي جهة (توظيف/جهة خارجية) من التحقق من صحة كشف الدرجات عبر
صفحة عامة على المسار /verify، دون تمكين أحد من فتح بيانات طالب لم يحصل على
رابط موقّع خاص به.

التوقيع: HMAC-SHA256 بمفتاح الموقع (encryption_key) — ثابت عبر إعادة التشغيل،
ولا يمكن توليد رابط صالح دون معرفة مفتاح الموقع.
"""

import base64
import hashlib
import hmac
from urllib.parse import urlencode

import frappe
from markupsafe import Markup

# وسم النطاق حتى لا يصلح توقيع مستند لنوع آخر مستقبلًا
_SCOPE = "transcript"


def _secret() -> bytes:
    from frappe.utils.password import get_encryption_key

    return get_encryption_key().encode()


def sign(student: str, program: str | None = None) -> str:
    """توقيع قصير ثابت لمفتاح (طالب، برنامج)."""
    message = f"{_SCOPE}|{student}|{program or ''}".encode()
    digest = hmac.new(_secret(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:22]


def is_valid(student: str, program: str | None, signature: str) -> bool:
    """تحقق ثابت الزمن من صحة التوقيع."""
    return hmac.compare_digest(signature or "", sign(student, program))


def base_url() -> str:
    """العنوان الأساسي المستخدَم في روابط التحقق (قابل للتجاوز عبر site_config)."""
    configured = frappe.get_conf().get("verification_base_url")
    return (configured or frappe.utils.get_url()).rstrip("/")


def verify_url(student: str, program: str | None = None) -> str:
    """رابط صفحة التحقق العام للطالب/البرنامج."""
    query = urlencode({"d": student, "p": program or "", "s": sign(student, program)})
    return f"{base_url()}/verify?{query}"


def qr_data_uri(text: str, scale: int = 3) -> str:
    """صورة QR بصيغة PNG مضمّنة (data URI) — مدعومة في wkhtmltopdf."""
    import pyqrcode

    code = pyqrcode.create(text, error="M")
    return "data:image/png;base64," + code.png_as_base64_str(scale=scale)


def verify_qr(student: str, program: str | None = None) -> Markup:
    """وسم <img> لرمز QR إلى صفحة التحقق — يُستدعى من قوالب الطباعة."""
    uri = qr_data_uri(verify_url(student, program))
    return Markup(f'<img class="verify-qr" src="{uri}" alt="QR">')
