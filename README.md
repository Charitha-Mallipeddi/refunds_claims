# Django Letters Demo (PDF + Email)

This is a minimal Django project that generates a **denial letter PDF** and renders the **email HTML** for the same message.

## Quick start
```bash
cd django_letters_demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000
# open http://127.0.0.1:8000/
```

- Click **Open Email HTML** → see the email version.
- Click **Create PDF** → it returns JSON with `download_url`; open it to fetch the PDF.

## API (if you want to POST custom data)
Both endpoints accept POSTed JSON (same structure) to override the sample data:

POST `/letters/email` → returns HTML body.  
POST `/letters/pdf` → creates a PDF in `media/letters` and returns a link.

### Sample payload
```json
{
  "order_id": "11111",
  "reason_code": "NO_REMAINING_VALUE",
  "customer": {
    "name": "Thomas Knierim",
    "email": "example@gmail.com",
    "address_line1": "2086 5th Avenue, Apt# 3A",
    "address_line2": "",
    "city": "New York",
    "state": "NY",
    "zip": "10035"
  },
  "body_vars": {
    "website_url": "https://www.new.mta.info",
    "contact_url": "https://contact.mta.info/s/customer-feedback",
    "support_phone": "(718) 217-5477"
  }
}
```

## Git & sync to office laptop
```bash
# in project root
git init
git add .
git commit -m "Initial Django letters demo"
# create a new GitHub repo (e.g., django-letters-demo) then:
git branch -M main
git remote add origin https://github.com/<your-username>/django-letters-demo.git
git push -u origin main
```

On your office laptop:
```bash
git clone https://github.com/<your-username>/django-letters-demo.git
cd django_letters_demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000
```

## Customizing
- Email HTML template: `templates/letters/denial_email.html`
- PDF body text template: `templates/letters/denial_body.txt`
- PDF output folder: `media/letters/`
