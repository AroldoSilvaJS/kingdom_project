# core/tests.py
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError

from economy.models import Wallet
from core.models import UserProfile, UserRole, KingdomSetting, AdminAuditLog
from idols.models import IdolProfile, Review, Post, PostUnlock, PostLike, CustomRequest, PostComment
from pets.models import Pet
from pets.species_registry import PET_SPECIES_REGISTRY, get_evolution_stage
from core.utils import grant_user_xp


class KingdomMasterTestSuite(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_id = 7474444797
        self.user_id = 123456789
        self.other_user_id = 987654321

        self.admin_role = UserRole.objects.create(telegram_id=self.admin_id, role='admin')
        self.user_role = UserRole.objects.create(telegram_id=self.user_id, role='cliente')
        self.other_role = UserRole.objects.create(telegram_id=self.other_user_id, role='cliente')

        self.user_wallet = Wallet.objects.create(telegram_user_id=self.user_id, balance=300)
        self.admin_wallet = Wallet.objects.create(telegram_user_id=self.admin_id, balance=1000)
        self.user_profile = UserProfile.objects.create(telegram_user_id=self.user_id, username="NobleAlexander")

    # --- BLOQUE 1: ECONOMÍA Y BONOS ---
    def test_wallet_initial_and_funds(self):
        w = Wallet.objects.create(telegram_user_id=111001)
        self.assertEqual(w.balance, 150)
        self.user_wallet.add_funds(50)
        self.assertEqual(self.user_wallet.balance, 350)
        self.assertTrue(self.user_wallet.remove_funds(100))
        self.assertEqual(self.user_wallet.balance, 250)
        self.assertFalse(self.user_wallet.remove_funds(500))

    def test_bonus_cooldowns_fox_stages(self):
        # Base sin zorro: 24h
        self.assertEqual(self.user_wallet.get_cooldown_hours(), 24)
        
        # Zorro Fase 1: 22h
        p = Pet.objects.create(telegram_user_id=self.user_id, name="K", species="fox", level=1)
        self.assertEqual(self.user_wallet.get_cooldown_hours(), 22)

        # Zorro Fase 2 (Lvl 10): 20h
        p.level = 10
        p.save()
        self.assertEqual(self.user_wallet.get_cooldown_hours(), 20)

        # Zorro Fase 3 (Lvl 25): 18h
        p.level = 25
        p.save()
        self.assertEqual(self.user_wallet.get_cooldown_hours(), 18)

    def test_claim_bonus_view(self):
        self.client.post(reverse('economy:claim_bonus'), {'tg_id': self.user_id})
        self.user_wallet.refresh_from_db()
        self.assertGreater(self.user_wallet.balance, 300)
        self.assertFalse(self.user_wallet.can_claim_bonus())

    # --- BLOQUE 2: PROGRESIÓN RPG Y NIVELES ---
    def test_xp_curve_and_ranks(self):
        # Lvl 1 requiere 235 EXP
        self.assertEqual(self.user_profile.xp_needed_for_next_level, 235)
        self.assertEqual(self.user_profile.get_daily_bonus_amount(), 26)
        self.assertIn("Curioso", self.user_profile.get_rank_name())

        # Escalafón de rangos
        self.user_profile.level = 12
        self.assertIn("Caballero", self.user_profile.get_rank_name())
        self.user_profile.level = 22
        self.assertIn("Conde", self.user_profile.get_rank_name())
        self.user_profile.level = 50
        self.assertIn("Duque", self.user_profile.get_rank_name())
        self.user_profile.level = 70
        self.assertIn("Soberano", self.user_profile.get_rank_name())

    def test_add_xp_and_level_up(self):
        leveled_up, new_lvl, reward = self.user_profile.add_xp(240)
        self.assertTrue(leveled_up)
        self.assertEqual(new_lvl, 2)
        self.assertEqual(reward, 15)

    def test_grant_user_xp_with_owl_buff(self):
        # Búho Cronos Fase 1 da +15% EXP extra
        Pet.objects.create(telegram_user_id=self.user_id, name="Stryx", species="owl", level=1)
        grant_user_xp(None, self.user_id, 100)
        self.user_profile.refresh_from_db()
        # 100 * 1.15 = 115 EXP
        self.assertEqual(self.user_profile.current_xp, 115)

    def test_max_bet_scaling(self):
        self.assertEqual(self.user_profile.max_bet_allowed, 20)
        self.user_profile.level = 16
        self.assertEqual(self.user_profile.max_bet_allowed, 80)
        self.user_profile.level = 35
        self.assertEqual(self.user_profile.max_bet_allowed, 150)

    # --- BLOQUE 3: LAS 10 MASCOTAS Y 3 EVOLUCIONES ---
    def test_all_10_species_registered(self):
        self.assertEqual(len(PET_SPECIES_REGISTRY), 10)
        expected = ['fox', 'panther', 'viper', 'raven', 'wolf', 'dragon', 'owl', 'deer', 'scorpion', 'rabbit']
        for sp in expected:
            self.assertIn(sp, PET_SPECIES_REGISTRY)

    def test_evolution_stages_and_sprites(self):
        # Fase 1 (Lvl 1)
        p = Pet.objects.create(telegram_user_id=self.user_id, name="Panth", species="panther", level=1)
        self.assertEqual(p.evolution_stage_number, 1)
        self.assertEqual(p.evolved_name, "Nocx")
        self.assertEqual(p.get_image_url(), "/media/pets/Nocx.png")

        # Fase 2 (Lvl 10)
        p.level = 10
        p.save()
        self.assertEqual(p.evolution_stage_number, 2)
        self.assertEqual(p.evolved_name, "Umbrather")
        self.assertEqual(p.get_image_url(), "/media/pets/Umbrather.png")

        # Fase 3 (Lvl 25)
        p.level = 25
        p.save()
        self.assertEqual(p.evolution_stage_number, 3)
        self.assertEqual(p.evolved_name, "Nyxador Soberano")
        self.assertEqual(p.get_image_url(), "/media/pets/Nyxador Soberano.png")

    def test_pet_feed_and_pet_actions(self):
        p = Pet.objects.create(telegram_user_id=self.user_id, name="P", species="panther", energy=50, xp=0)
        p.feed()       # 50 + 25 = 75 energía | felicidad: 70 + 10 = 80
        self.assertEqual(p.energy, 75)
        self.assertEqual(p.xp, 20)
        p.pet_action() # felicidad: 80 + 20 = 100
        self.assertEqual(p.happiness, 100)
        self.assertEqual(p.xp, 35)

    def test_pet_interact_views_ajax(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="P", species="panther")
        res1 = self.client.post('/pets/interact/', {'tg_id': self.user_id, 'action': 'feed', 'ajax': '1'})
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.json()['success'])

        res2 = self.client.post('/pets/interact/', {'tg_id': self.user_id, 'action': 'pet', 'ajax': '1'})
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.json()['success'])

    def test_pet_transmutation(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Old", species="panther")
        self.client.post('/pets/change/', {'tg_id': self.user_id, 'new_species': 'dragon', 'new_name': 'Draco'})
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 0)
        pet = Pet.objects.get(telegram_user_id=self.user_id)
        self.assertEqual(pet.species, 'dragon')
        self.assertEqual(pet.evolved_name, 'Drakito')

    # --- BLOQUE 4: IDOLS, FANS Y PHOTOCARDS ---
    def test_idol_max_2_validation(self):
        IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="I1", bio="B")
        IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="I2", bio="B")
        third = IdolProfile(telegram_user_id=self.user_id, stage_name="I3", bio="B")
        with self.assertRaises(ValidationError):
            third.clean()

    def test_vip_post_unlock_with_viper_discount(self):
        # Víbora Fase 1: 15% descuento (paga 85 🪙 de 100 🪙)
        Pet.objects.create(telegram_user_id=self.user_id, name="S", species="viper", level=1)
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        post = Post.objects.create(idol=idol, network='fans', price=100, caption="VIP")
        
        self.client.post(reverse('idols:unlock_post', args=[post.id]), {'tg_id': self.user_id})
        self.user_wallet.refresh_from_db()
        # 300 - 85 = 215
        self.assertEqual(self.user_wallet.balance, 215)
        self.assertTrue(PostUnlock.objects.filter(post=post, client_telegram_id=self.user_id).exists())

    def test_post_like_toggle(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        post = Post.objects.create(idol=idol, network='gram', caption="Foto")
        r1 = self.client.post(reverse('idols:toggle_like', args=[post.id]), {'tg_id': self.user_id})
        self.assertTrue(r1.json()['liked'])
        r2 = self.client.post(reverse('idols:toggle_like', args=[post.id]), {'tg_id': self.user_id})
        self.assertFalse(r2.json()['liked'])

    # --- BLOQUE 5: CASINO Y JUEGOS (RESPETANDO MAX_BET = 20 A LVL 1) ---
    def test_casino_roulette_bet_cap_at_level1(self):
        # A nivel 1 el max_bet es 20. Una apuesta de 150 debe ser rechazada
        self.client.post(reverse('economy:casino'), {'tg_id': self.user_id, 'bet_amount': 150, 'bet_choice': 'red'})
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    def test_casino_roulette_valid_bet_ajax(self):
        # Apuesta válida de 10 🪙 (dentro de max_bet = 20)
        res = self.client.post(reverse('economy:casino'), {'tg_id': self.user_id, 'bet_amount': 10, 'bet_choice': 'red', 'ajax': '1'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])

    def test_slots_spin_valid_ajax(self):
        # Apuesta válida de 10 🪙
        res = self.client.post(reverse('economy:slots'), {'tg_id': self.user_id, 'bet_amount': 10, 'ajax': '1'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])

    def test_blackjack_deal_within_max_bet(self):
        # Apuesta válida de 20 🪙 (tope a nivel 1)
        res = self.client.post(reverse('economy:blackjack'), {'tg_id': self.user_id, 'action': 'deal', 'bet_amount': 20, 'ajax': '1'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.user_wallet.refresh_from_db()
        # Saldo descontado o ganado con blackjack natural
        self.assertTrue(self.user_wallet.balance <= 280 or self.user_wallet.balance == 350)

    def test_mines_start_game_ajax(self):
        res = self.client.post(reverse('economy:mines'), {
            'tg_id': self.user_id,
            'action': 'start',
            'bet_amount': 20,
            'mines_count': 3,
            'ajax': '1'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertEqual(res.json()['bet'], 20)

    # --- BLOQUE 6: SALA DEL TRONO Y ADMIN ---
    def test_admin_panel_access_and_adjust_gold(self):
        res_forbidden = self.client.get(f'/admin-panel/?tg_id={self.user_id}')
        self.assertEqual(res_forbidden.status_code, 302)

        res_ok = self.client.get(f'/admin-panel/?tg_id={self.admin_id}')
        self.assertEqual(res_ok.status_code, 200)

        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'adjust_gold',
            'mode': 'add',
            'amount': 100,
            'target_id': self.user_id
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 400)
        self.assertTrue(AdminAuditLog.objects.filter(target_tg_id=self.user_id).exists())

    def test_final_system_integrity(self):
        self.assertEqual(UserRole.objects.count(), 3)
        self.assertEqual(Wallet.objects.count(), 2)
        self.assertEqual(UserProfile.objects.count(), 1)