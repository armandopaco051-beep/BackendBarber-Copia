import os
import sys

import requests
from dotenv import load_dotenv


def leer_frontend_public_key():
    frontend_env = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Frontend_Barberia', '.env'))
    if not os.path.exists(frontend_env):
        return ''

    with open(frontend_env, 'r', encoding='utf-8') as archivo:
        for linea in archivo:
            if linea.startswith('VITE_STRIPE_PUBLIC_KEY='):
                return linea.split('=', 1)[1].strip()
    return ''


def main():
    load_dotenv()
    secret_key = os.getenv('STRIPE_SECRET_KEY', '').strip()
    public_key = leer_frontend_public_key()

    if not secret_key:
        print('ERROR: Falta STRIPE_SECRET_KEY en el .env del backend.')
        return 1
    if not public_key:
        print('ERROR: Falta VITE_STRIPE_PUBLIC_KEY en el .env del frontend.')
        return 1

    payment_intents = requests.get(
        'https://api.stripe.com/v1/payment_intents',
        params={'limit': 1},
        auth=(secret_key, ''),
        timeout=20,
    )
    print(f'STRIPE_SECRET_KEY status: {payment_intents.status_code}')
    if payment_intents.status_code != 200:
        print(payment_intents.text)
        return 1

    data = payment_intents.json().get('data', [])
    if not data:
        print('No hay PaymentIntents para validar la clave publica.')
        return 0

    client_secret = data[0].get('client_secret')
    elements_session = requests.get(
        'https://api.stripe.com/v1/elements/sessions',
        params={
            'client_secret': client_secret,
            'key': public_key,
            '_stripe_version': '2026-03-25.dahlia',
            'elements_init_source': 'stripe.elements',
            'locale': 'es-ES',
            'type': 'payment_intent',
        },
        timeout=20,
    )
    print(f'VITE_STRIPE_PUBLIC_KEY status: {elements_session.status_code}')
    if elements_session.status_code == 401:
        print('ERROR: La clave publica pk_test del frontend es invalida o no corresponde a la misma cuenta Stripe.')
        print(elements_session.text)
        return 1

    print('OK: Las claves Stripe son compatibles.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
