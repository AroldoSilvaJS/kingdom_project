from django.test import TestCase, Client
from django.urls import reverse
from economy.models import Wallet
from core.models import UserProfile
from idols.models import UserRole, IdolProfile, Post, PostUnlock
from pets.models import Pet

class KingdomOfPleasureTestSuite(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_tg_id = '7474444797'
        self.user_tg_id = '123456789'
        
        # 1. Crear billeteras de prueba
        self.wallet = Wallet.objects.create(telegram_user_id=123456789, balance=200)
        self.admin_wallet = Wallet.objects.create(telegram_user_id=7474444797, balance=1000)

    def test_01_wallet_economy(self):
        """Verifica que la billetera sume, reste y valide saldo correctamente"""
        # Sumar fondos
        self.wallet.add_funds(50)
        self.assertEqual(self.wallet.balance, 250)
        
        # Restar fondos válidos
        res = self.wallet.remove_funds(100)
        self.assertTrue(res)
        self.assertEqual(self.wallet.balance, 150)
        
        # Intentar gastar más de lo que tiene
        res_fail = self.wallet.remove_funds(500)
        self.assertFalse(res_fail)
        self.assertEqual(self.wallet.balance, 150)

    def test_02_pet_system(self):
        """Verifica adopción, alimentación y subida de nivel de mascotas"""
        pet = Pet.objects.create(
            telegram_user_id=123456789,
            name="Kuro",
            species="pantera",
            level=1,
            xp=0,
            energy=50
        )
        # Alimentar (+25 energía, +30 xp)
        pet.feed()
        self.assertEqual(pet.energy, 75)
        self.assertEqual(pet.xp, 30)
        self.assertEqual(pet.level, 1)

    def test_03_admin_panel_security(self):
        """Verifica que un usuario común NO pueda entrar al Panel VIP"""
        # Intento de usuario normal (debe redirigir)
        response_user = self.client.get(f'/admin-panel/?tg_id={self.user_tg_id}')
        self.assertEqual(response_user.status_code, 302)

        # Intento de ADMIN real (debe dar 200 OK)
        response_admin = self.client.get(f'/admin-panel/?tg_id={self.admin_tg_id}')
        self.assertEqual(response_admin.status_code, 200)

    def test_04_profile_customization(self):
        """Verifica que el Pasaporte Noble guarde títulos, marcos y temas"""
        profile = UserProfile.objects.create(
            telegram_user_id=123456789,
            username="LordAlexander",
            title="duque",
            avatar_frame="gold",
            motto="Gloria y Placer",
            profile_theme="velvet"
        )
        self.assertEqual(profile.title, "duque")
        self.assertEqual(profile.motto, "Gloria y Placer")

    def test_05_vip_unlock_commission(self):
        """Verifica el split financiero de fotos VIP (15% comisión / 85% Idol)"""
        idol = IdolProfile.objects.create(
            telegram_user_id=888888,
            stage_name="Scarlett",
            bio="Musa"
        )
        post = Post.objects.create(
            idol=idol,
            network='fans',
            price=100,
            caption="Exclusivo"
        )
        # Desbloqueo
        response = self.client.post(reverse('idols:unlock_post', args=[post.id]), {
            'tg_id': 123456789
        })
        self.wallet.refresh_from_db()
        # El cliente gastó 100 🪙
        self.assertEqual(self.wallet.balance, 100)
        # La Idol recibió 85 🪙 (85%)
        idol_wallet = Wallet.objects.get(telegram_user_id=888888)
        self.assertEqual(idol_wallet.balance, 235) # 150 base + 85