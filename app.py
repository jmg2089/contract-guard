import os
import smtplib
from pathlib import Path
from email.message import EmailMessage

from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

from pathlib import Path
from html import escape


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True)

app = Flask(__name__)

print(".env 위치:", ENV_PATH)
print(".env 존재 여부:", ENV_PATH.exists())
print("SMTP_USERNAME 설정:", bool(os.getenv("SMTP_USERNAME")))
print("SMTP_PASSWORD 설정:", bool(os.getenv("SMTP_PASSWORD")))
print("CONTACT_RECEIVER 설정:", bool(os.getenv("CONTACT_RECEIVER")))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/contact", methods=["POST"])
def send_contact_email():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    reply_email = str(data.get("email", "")).strip()
    category = str(data.get("category", "")).strip()
    message = str(data.get("message", "")).strip()
    privacy_agreement = data.get("privacyAgreement", False)

    if not all([
        name,
        reply_email,
        category,
        message,
        privacy_agreement
    ]):
        return jsonify({
            "success": False,
            "message": "필수 항목을 모두 입력해 주세요."
        }), 400

    if "@" not in reply_email:
        return jsonify({
            "success": False,
            "message": "올바른 이메일 주소를 입력해 주세요."
        }), 400

    if len(message) > 1000:
        return jsonify({
            "success": False,
            "message": "문의 내용은 1,000자 이하로 입력해 주세요."
        }), 400

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    contact_receiver = os.getenv("CONTACT_RECEIVER")

    print("SMTP 서버:", smtp_host)
    print("SMTP 포트:", smtp_port)
    print("SMTP 계정:", repr(smtp_username))
    print("SMTP 비밀번호 길이:", len(smtp_password or ""))
    print("수신 주소 설정:", bool(contact_receiver))

    if not all([
        smtp_username,
        smtp_password,
        contact_receiver
    ]):
        app.logger.error("메일 환경변수가 설정되지 않았습니다.")

        return jsonify({
            "success": False,
            "message": "메일 발송 설정이 완료되지 않았습니다."
        }), 500

    category_names = {
        "service": "서비스 이용 문의",
        "analysis": "계약서 점검 결과 문의",
        "privacy": "개인정보 및 보안 문의",
        "partnership": "제휴 및 협업 문의",
        "other": "기타 문의"
    }

    category_name = category_names.get(category, "기타 문의")

    smtp_from = os.getenv("SMTP_FROM", "wendy132@naver.com")

    email_message = EmailMessage()
    email_message["Subject"] = f"[Overfit 문의] {category_name}"
    email_message["From"] = smtp_from
    email_message["To"] = contact_receiver
    email_message["Reply-To"] = reply_email

    afe_name = escape(name)
    safe_reply_email = escape(reply_email)
    safe_category_name = escape(category_name)
    safe_message = escape(message).replace("\n", "<br>")

    safe_name = escape(name)
    safe_reply_email = escape(reply_email)
    safe_category_name = escape(category_name)
    safe_message = escape(message).replace("\n", "<br>")

    logo_path = Path(app.root_path) / "static" / "images" / "image.png"

    email_message.set_content(
        f"""
    Overfit 웹사이트에서 문의가 접수되었습니다.

    이름: {name}
    답변받을 이메일: {reply_email}
    문의 유형: {category_name}

    문의 내용
    ────────────────────────
    {message}
    ────────────────────────

    본 메일은 Overfit 웹사이트에서 자동으로 발송되었습니다.
        """.strip()
    )

    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
    </head>

    <body style="
        margin: 0;
        padding: 0;
        background-color: #f4f7fb;
        font-family: Arial, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
        color: #172033;
    ">
        <table
            role="presentation"
            width="100%"
            cellspacing="0"
            cellpadding="0"
            style="background-color: #f4f7fb; padding: 40px 16px;"
        >
            <tr>
                <td align="center">
                    <table
                        role="presentation"
                        width="100%"
                        cellspacing="0"
                        cellpadding="0"
                        style="
                            max-width: 620px;
                            background-color: #ffffff;
                            border: 1px solid #e3e8ef;
                            border-radius: 16px;
                            overflow: hidden;
                        "
                    >
                        <tr>
                            <td style="
                                padding: 28px 34px;
                                border-bottom: 1px solid #e8edf3;
                            ">
                                <table
                                    role="presentation"
                                    cellspacing="0"
                                    cellpadding="0"
                                >
                                    <tr>
                                        <td style="padding-right: 14px;">
                                            <img
                                                src="cid:overfit-logo"
                                                alt="Overfit"
                                                width="48"
                                                style="
                                                    display: block;
                                                    width: 48px;
                                                    height: auto;
                                                "
                                            >
                                        </td>

                                        <td>
                                            <div style="
                                                color: #10243e;
                                                font-size: 21px;
                                                font-weight: 700;
                                                line-height: 1.3;
                                            ">
                                                Overfit
                                            </div>

                                            <div style="
                                                margin-top: 3px;
                                                color: #718096;
                                                font-size: 12px;
                                            ">
                                                근로계약서 사전 점검 서비스
                                            </div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 36px 34px 20px;">
                                <div style="
                                    color: #2563eb;
                                    font-size: 13px;
                                    font-weight: 700;
                                    letter-spacing: 0.3px;
                                ">
                                    CONTACT REQUEST
                                </div>

                                <h1 style="
                                    margin: 10px 0 12px;
                                    color: #10243e;
                                    font-size: 25px;
                                    line-height: 1.4;
                                ">
                                    새로운 문의가 접수되었습니다.
                                </h1>

                                <p style="
                                    margin: 0;
                                    color: #64748b;
                                    font-size: 14px;
                                    line-height: 1.7;
                                ">
                                    Overfit 웹사이트 문의 양식을 통해 접수된 내용입니다.
                                    아래 정보를 확인한 후 문의자에게 답변해 주세요.
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 16px 34px;">
                                <table
                                    role="presentation"
                                    width="100%"
                                    cellspacing="0"
                                    cellpadding="0"
                                    style="
                                        background-color: #f8fafc;
                                        border: 1px solid #e5eaf0;
                                        border-radius: 10px;
                                    "
                                >
                                    <tr>
                                        <td style="
                                            width: 130px;
                                            padding: 16px 18px;
                                            color: #64748b;
                                            font-size: 13px;
                                            border-bottom: 1px solid #e5eaf0;
                                        ">
                                            이름
                                        </td>

                                        <td style="
                                            padding: 16px 18px;
                                            color: #172033;
                                            font-size: 14px;
                                            font-weight: 600;
                                            border-bottom: 1px solid #e5eaf0;
                                        ">
                                            {safe_name}
                                        </td>
                                    </tr>

                                    <tr>
                                        <td style="
                                            padding: 16px 18px;
                                            color: #64748b;
                                            font-size: 13px;
                                            border-bottom: 1px solid #e5eaf0;
                                        ">
                                            이메일
                                        </td>

                                        <td style="
                                            padding: 16px 18px;
                                            font-size: 14px;
                                            border-bottom: 1px solid #e5eaf0;
                                        ">
                                            <a
                                                href="mailto:{safe_reply_email}"
                                                style="
                                                    color: #2563eb;
                                                    text-decoration: none;
                                                "
                                            >
                                                {safe_reply_email}
                                            </a>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="
                                            padding: 16px 18px;
                                            color: #64748b;
                                            font-size: 13px;
                                        ">
                                            문의 유형
                                        </td>

                                        <td style="
                                            padding: 16px 18px;
                                            color: #172033;
                                            font-size: 14px;
                                            font-weight: 600;
                                        ">
                                            {safe_category_name}
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 18px 34px 38px;">
                                <div style="
                                    margin-bottom: 10px;
                                    color: #334155;
                                    font-size: 14px;
                                    font-weight: 700;
                                ">
                                    문의 내용
                                </div>
                                <div style="
                                    min-height: 120px;
                                    padding: 20px;
                                    background-color: #ffffff;
                                    border: 1px solid #dfe5ec;
                                    border-left: 4px solid #2563eb;
                                    border-radius: 8px;
                                    color: #334155;
                                    font-size: 14px;
                                    line-height: 1.8;
                                    word-break: break-word;
                                ">
                                    {safe_message}
                                </div>
                            </td>
                        </tr>
                        <tr>
                            <td style="
                                padding: 22px 34px;
                                background-color: #10243e;
                                color: #cbd5e1;
                                font-size: 11px;
                                line-height: 1.7;
                            ">
                                본 메일은 Overfit 웹사이트에서 자동으로 발송되었습니다.
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    email_message.add_alternative(html_content, subtype="html")

    if logo_path.exists():
        with open(logo_path, "rb") as logo_file:
            logo_data = logo_file.read()

        html_part = email_message.get_payload()[-1]

        html_part.add_related(
            logo_data,
            maintype="image",
            subtype="png",
            cid="<overfit-logo>",
            filename="overfit-logo.png"
        )
    else:
        app.logger.warning("메일 로고 파일을 찾을 수 없습니다: %s", logo_path)

    try:
        with smtplib.SMTP_SSL(
            smtp_host,
            smtp_port,
            timeout=10
        ) as smtp:
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(email_message)

    except smtplib.SMTPAuthenticationError:
        app.logger.exception("SMTP 인증에 실패했습니다.")

        return jsonify({
            "success": False,
            "message": "메일 계정 인증에 실패했습니다."
        }), 500

    except Exception:
        app.logger.exception("문의 메일 발송 중 오류가 발생했습니다.")

        return jsonify({
            "success": False,
            "message": "메일 발송에 실패했습니다. 잠시 후 다시 시도해 주세요."
        }), 500

    return jsonify({
        "success": True,
        "message": "문의가 정상적으로 전송되었습니다."
    })

if __name__ == "__main__":
    app.run(debug=True, port=5001)