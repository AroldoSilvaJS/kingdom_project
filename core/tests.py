import json
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError

from economy.models import Wallet
from core.models import UserProfile, UserRole, KingdomSetting, AdminAuditLog
from idols.models import IdolProfile, Review, Post, PostUnlock, PostLike, CustomRequest, PostComment
from pets.models import Pet
from core.utils import grant_user_xp


class Kingdom200ImperialMasterTestSuite(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_id = 7474444797
        self.user_id = 123456789
        self.other_user_id = 987654321

        # Roles
        self.admin_role = UserRole.objects.create(telegram_id=self.admin_id, role='admin')
        self.user_role = UserRole.objects.create(telegram_id=self.user_id, role='cliente')
        self.other_role = UserRole.objects.create(telegram_id=self.other_user_id, role='cliente')

        # Wallets
        self.user_wallet = Wallet.objects.create(telegram_user_id=self.user_id, balance=300)
        self.admin_wallet = Wallet.objects.create(telegram_user_id=self.admin_id, balance=1000)

        # Profiles
        self.user_profile = UserProfile.objects.create(telegram_user_id=self.user_id, username="NobleAlexander")

    # ==========================================
    # BLOQUE 1: ECONOMÍA Y BILLETERAS (1 - 35)
    # ==========================================
    def test_001_wallet_initial_balance_default(self):
        w = Wallet.objects.create(telegram_user_id=111001)
        self.assertEqual(w.balance, 150)

    def test_002_wallet_add_funds(self):
        self.user_wallet.add_funds(50)
        self.assertEqual(self.user_wallet.balance, 350)

    def test_003_wallet_remove_funds_success(self):
        success = self.user_wallet.remove_funds(100)
        self.assertTrue(success)
        self.assertEqual(self.user_wallet.balance, 200)

    def test_004_wallet_remove_funds_insufficient(self):
        success = self.user_wallet.remove_funds(500)
        self.assertFalse(success)
        self.assertEqual(self.user_wallet.balance, 300)

    def test_005_wallet_remove_exact_balance(self):
        success = self.user_wallet.remove_funds(300)
        self.assertTrue(success)
        self.assertEqual(self.user_wallet.balance, 0)

    def test_006_wallet_can_claim_bonus_initially(self):
        self.assertTrue(self.user_wallet.can_claim_bonus())
        self.assertEqual(self.user_wallet.seconds_until_next_bonus(), 0)

    def test_007_wallet_cannot_claim_bonus_within_24h(self):
        self.user_wallet.last_bonus_claim = timezone.now()
        self.user_wallet.save()
        self.assertFalse(self.user_wallet.can_claim_bonus())
        self.assertGreater(self.user_wallet.seconds_until_next_bonus(), 0)

    def test_008_wallet_can_claim_bonus_after_24h(self):
        self.user_wallet.last_bonus_claim = timezone.now() - timedelta(hours=25)
        self.user_wallet.save()
        self.assertTrue(self.user_wallet.can_claim_bonus())
        self.assertEqual(self.user_wallet.seconds_until_next_bonus(), 0)

    def test_009_wallet_cooldown_hours_default_is_24(self):
        self.assertEqual(self.user_wallet.get_cooldown_hours(), 24)

    def test_010_wallet_cooldown_hours_fox_is_22(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Kitsu", species="fox")
        self.assertEqual(self.user_wallet.get_cooldown_hours(), 22)

    def test_011_wallet_bonus_claimed_updates_timestamp(self):
        self.assertIsNone(self.user_wallet.last_bonus_claim)
        self.client.post(reverse('economy:claim_bonus'), {'tg_id': self.user_id})
        self.user_wallet.refresh_from_db()
        self.assertIsNotNone(self.user_wallet.last_bonus_claim)

    def test_012_wallet_double_claim_bonus_blocked(self):
        self.client.post(reverse('economy:claim_bonus'), {'tg_id': self.user_id})
        self.user_wallet.refresh_from_db()
        bal_after_first = self.user_wallet.balance
        # Segundo reclamo inmediato bloqueado
        self.client.post(reverse('economy:claim_bonus'), {'tg_id': self.user_id})
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, bal_after_first)

    def test_013_wallet_add_zero_funds(self):
        self.user_wallet.add_funds(0)
        self.assertEqual(self.user_wallet.balance, 300)

    def test_014_wallet_add_large_funds(self):
        self.user_wallet.add_funds(100000)
        self.assertEqual(self.user_wallet.balance, 100300)

    def test_015_wallet_remove_zero_funds(self):
        success = self.user_wallet.remove_funds(0)
        self.assertTrue(success)
        self.assertEqual(self.user_wallet.balance, 300)

    def test_016_wallet_remove_negative_funds(self):
        # Aseguramos que remove_funds con monto mayor no pase
        success = self.user_wallet.remove_funds(301)
        self.assertFalse(success)
        self.assertEqual(self.user_wallet.balance, 300)

    def test_017_wallet_str_representation(self):
        self.assertIn("Wallet 123456789", str(self.user_wallet))
        self.assertIn("300", str(self.user_wallet))

    def test_018_wallet_seconds_until_bonus_zero_when_none(self):
        self.assertEqual(self.user_wallet.seconds_until_next_bonus(), 0)

    def test_019_wallet_seconds_until_bonus_accurate_when_recent(self):
        self.user_wallet.last_bonus_claim = timezone.now() - timedelta(hours=1)
        self.user_wallet.save()
        secs = self.user_wallet.seconds_until_next_bonus()
        # Restan ~23 horas = ~82800 seg
        self.assertTrue(80000 < secs < 83000)

    def test_020_wallet_fox_seconds_until_bonus_reduced(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Kitsu", species="fox")
        self.user_wallet.last_bonus_claim = timezone.now() - timedelta(hours=1)
        self.user_wallet.save()
        secs = self.user_wallet.seconds_until_next_bonus()
        # Restan ~21 horas = ~75600 seg
        self.assertTrue(73000 < secs < 76000)

    def test_021_wallet_dashboard_loads_status_200(self):
        res = self.client.get(f'/economy/wallet/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_022_wallet_dashboard_creates_wallet_if_not_exists(self):
        new_id = 999111
        self.client.get(f'/economy/wallet/?tg_id={new_id}')
        self.assertTrue(Wallet.objects.filter(telegram_user_id=new_id).exists())

    def test_023_wallet_unique_telegram_id_constraint(self):
        with self.assertRaises(Exception):
            Wallet.objects.create(telegram_user_id=self.user_id, balance=500)

    def test_024_wallet_balance_preserved_across_queries(self):
        w = Wallet.objects.get(telegram_user_id=self.user_id)
        self.assertEqual(w.balance, 300)

    def test_025_wallet_add_funds_multiple_times(self):
        self.user_wallet.add_funds(10)
        self.user_wallet.add_funds(20)
        self.user_wallet.add_funds(30)
        self.assertEqual(self.user_wallet.balance, 360)

    def test_026_wallet_remove_funds_multiple_times(self):
        self.user_wallet.remove_funds(50)
        self.user_wallet.remove_funds(50)
        self.assertEqual(self.user_wallet.balance, 200)

    def test_027_wallet_last_bonus_claim_persisted(self):
        t = timezone.now()
        self.user_wallet.last_bonus_claim = t
        self.user_wallet.save()
        self.user_wallet.refresh_from_db()
        self.assertIsNotNone(self.user_wallet.last_bonus_claim)

    def test_028_wallet_created_at_is_auto_now(self):
        self.assertIsNotNone(self.user_wallet.created_at)

    def test_029_wallet_updated_at_is_auto_now(self):
        old_updated = self.user_wallet.updated_at
        self.user_wallet.add_funds(1)
        self.user_wallet.refresh_from_db()
        self.assertGreaterEqual(self.user_wallet.updated_at, old_updated)

    def test_030_wallet_claim_bonus_grants_positive_gold(self):
        init_bal = self.user_wallet.balance
        self.client.post(reverse('economy:claim_bonus'), {'tg_id': self.user_id})
        self.user_wallet.refresh_from_db()
        self.assertGreater(self.user_wallet.balance, init_bal)

    def test_031_wallet_claim_bonus_scales_with_higher_level(self):
        self.user_profile.level = 10
        self.user_profile.save()
        self.client.post(reverse('economy:claim_bonus'), {'tg_id': self.user_id})
        self.user_wallet.refresh_from_db()
        # Min premio 25 + (10 * 2) = 45 oro ganado
        self.assertGreaterEqual(self.user_wallet.balance - 300, 45)

    def test_032_wallet_cannot_claim_bonus_after_21h_normal(self):
        self.user_wallet.last_bonus_claim = timezone.now() - timedelta(hours=21)
        self.user_wallet.save()
        self.assertFalse(self.user_wallet.can_claim_bonus())

    def test_033_wallet_can_claim_bonus_after_23h_fox(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Kitsu", species="fox")
        self.user_wallet.last_bonus_claim = timezone.now() - timedelta(hours=23)
        self.user_wallet.save()
        self.assertTrue(self.user_wallet.can_claim_bonus())

    def test_034_wallet_seconds_until_bonus_zero_after_expiry(self):
        self.user_wallet.last_bonus_claim = timezone.now() - timedelta(hours=25)
        self.user_wallet.save()
        self.assertEqual(self.user_wallet.seconds_until_next_bonus(), 0)

    def test_035_wallet_remove_funds_insufficient_does_not_modify_balance(self):
        self.user_wallet.remove_funds(999999)
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    # ==========================================
    # BLOQUE 2: SISTEMA DE EXP Y NIVELES (36 - 70)
    # ==========================================
    def test_036_user_profile_initial_level_and_xp(self):
        self.assertEqual(self.user_profile.level, 1)
        self.assertEqual(self.user_profile.current_xp, 0)
        self.assertEqual(self.user_profile.total_xp, 0)

    def test_037_user_profile_xp_needed_level_1(self):
        self.assertEqual(self.user_profile.xp_needed_for_next_level, 100)

    def test_038_user_profile_xp_needed_level_2(self):
        self.user_profile.level = 2
        self.assertEqual(self.user_profile.xp_needed_for_next_level, 155)

    def test_039_user_profile_xp_progress_percentage_half(self):
        self.user_profile.current_xp = 50
        self.assertEqual(self.user_profile.xp_progress_percentage, 50)

    def test_040_user_profile_xp_progress_percentage_zero(self):
        self.assertEqual(self.user_profile.xp_progress_percentage, 0)

    def test_041_user_profile_xp_progress_percentage_capped_100(self):
        self.user_profile.current_xp = 150
        self.assertEqual(self.user_profile.xp_progress_percentage, 100)

    def test_042_user_profile_rank_name_level_1(self):
        self.assertIn("Curioso", self.user_profile.get_rank_name())

    def test_043_user_profile_rank_name_level_8(self):
        self.user_profile.level = 8
        self.assertIn("Caballero", self.user_profile.get_rank_name())

    def test_044_user_profile_rank_name_level_18(self):
        self.user_profile.level = 18
        self.assertIn("Conde", self.user_profile.get_rank_name())

    def test_045_user_profile_rank_name_level_30(self):
        self.user_profile.level = 30
        self.assertIn("Duque", self.user_profile.get_rank_name())

    def test_046_user_profile_rank_name_level_45(self):
        self.user_profile.level = 45
        self.assertIn("Archiduque", self.user_profile.get_rank_name())

    def test_047_user_profile_daily_bonus_scaling_lvl1(self):
        self.assertEqual(self.user_profile.get_daily_bonus_amount(), 35)

    def test_048_user_profile_daily_bonus_scaling_lvl10(self):
        self.user_profile.level = 10
        self.assertEqual(self.user_profile.get_daily_bonus_amount(), 40)

    def test_049_user_profile_daily_bonus_scaling_lvl25(self):
        self.user_profile.level = 25
        self.assertEqual(self.user_profile.get_daily_bonus_amount(), 45)

    def test_050_user_profile_daily_bonus_scaling_lvl45(self):
        self.user_profile.level = 45
        self.assertEqual(self.user_profile.get_daily_bonus_amount(), 50)

    def test_051_add_xp_without_level_up(self):
        leveled_up, new_level, reward = self.user_profile.add_xp(40)
        self.assertFalse(leveled_up)
        self.assertEqual(new_level, 1)
        self.assertEqual(self.user_profile.current_xp, 40)
        self.assertEqual(self.user_profile.total_xp, 40)
        self.assertEqual(reward, 0)

    def test_052_add_xp_with_single_level_up(self):
        leveled_up, new_level, reward = self.user_profile.add_xp(105)
        self.assertTrue(leveled_up)
        self.assertEqual(new_level, 2)
        self.assertEqual(self.user_profile.current_xp, 5)
        self.assertEqual(reward, 15 + (2 * 2))

    def test_053_add_xp_multi_level_jump(self):
        leveled_up, new_level, reward = self.user_profile.add_xp(400)
        self.assertTrue(leveled_up)
        self.assertEqual(new_level, 3)
        self.assertGreater(reward, 35)

    def test_054_grant_user_xp_utility_function(self):
        init_bal = self.user_wallet.balance
        grant_user_xp(None, self.user_id, 100, reason="Test Grant")
        self.user_wallet.refresh_from_db()
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.level, 2)
        self.assertEqual(self.user_wallet.balance, init_bal + 19)

    def test_055_grant_user_xp_handles_none_gracefully(self):
        grant_user_xp(None, None, 100)
        # No debe lanzar ninguna excepcion
        self.assertTrue(True)

    def test_056_grant_user_xp_handles_invalid_string_id(self):
        grant_user_xp(None, "None", 100)
        grant_user_xp(None, "", 100)
        self.assertTrue(True)

    def test_057_user_profile_str_representation(self):
        self.assertIn("NobleAlexander", str(self.user_profile))
        self.assertIn("Nivel 1", str(self.user_profile))

    def test_058_user_profile_theme_default_is_velvet(self):
        self.assertEqual(self.user_profile.profile_theme, 'velvet')

    def test_059_user_profile_avatar_frame_default_is_gold(self):
        self.assertEqual(self.user_profile.avatar_frame, 'gold')

    def test_060_user_profile_vip_badge_default_is_none(self):
        self.assertEqual(self.user_profile.vip_badge, 'none')

    def test_061_user_profile_customization_post_update(self):
        self.client.post(reverse('core:my_profile'), {
            'tg_id': self.user_id,
            'username': 'EmperadorNero',
            'motto': 'Honor y Fortuna',
            'profile_theme': 'crimson',
            'avatar_frame': 'flame',
            'vip_badge': 'high_roller'
        })
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.username, 'EmperadorNero')
        self.assertEqual(self.user_profile.profile_theme, 'crimson')
        self.assertEqual(self.user_profile.avatar_frame, 'flame')

    def test_062_user_profile_favorite_idol_assignment(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="Bio")
        self.user_profile.favorite_idol = idol
        self.user_profile.save()
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.favorite_idol, idol)

    def test_063_user_profile_created_at_is_auto_now(self):
        self.assertIsNotNone(self.user_profile.created_at)

    def test_064_user_profile_unique_telegram_id(self):
        with self.assertRaises(Exception):
            UserProfile.objects.create(telegram_user_id=self.user_id)

    def test_065_user_profile_total_xp_accumulates_correctly(self):
        self.user_profile.add_xp(50)
        self.user_profile.add_xp(60)
        self.assertEqual(self.user_profile.total_xp, 110)

    def test_066_user_profile_title_choices_valid(self):
        self.user_profile.title = 'duque'
        self.user_profile.save()
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.title, 'duque')

    def test_067_leaderboard_view_status_200(self):
        res = self.client.get(f'/salon-de-la-fama/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_068_profile_view_status_200(self):
        res = self.client.get(f'/profile/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_069_profile_view_without_tg_id_redirects(self):
        res = self.client.get('/profile/')
        self.assertEqual(res.status_code, 302)

    def test_070_profile_view_contains_achievements(self):
        res = self.client.get(f'/profile/?tg_id={self.user_id}')
        self.assertIn('achievements', res.context)

    # ==========================================
    # BLOQUE 3: ROLES, ADMIN & SALA DEL TRONO (71 - 105)
    # ==========================================
    def test_071_admin_panel_forbidden_for_clients(self):
        res = self.client.get(f'/admin-panel/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 302)

    def test_072_admin_panel_accessible_for_admin(self):
        res = self.client.get(f'/admin-panel/?tg_id={self.admin_id}')
        self.assertEqual(res.status_code, 200)

    def test_073_admin_adjust_gold_add(self):
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'adjust_gold',
            'mode': 'add',
            'amount': 150,
            'target_id': self.user_id
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 450)
        self.assertTrue(AdminAuditLog.objects.filter(action='gold_adjust').exists())

    def test_074_admin_adjust_gold_subtract(self):
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'adjust_gold',
            'mode': 'subtract',
            'amount': 100,
            'target_id': self.user_id
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 200)

    def test_075_admin_adjust_gold_set_exact(self):
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'adjust_gold',
            'mode': 'set',
            'amount': 777,
            'target_id': self.user_id
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 777)

    def test_076_admin_mass_gold_drop(self):
        other_w = Wallet.objects.create(telegram_user_id=self.other_user_id, balance=100)
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'mass_gold',
            'amount': 50
        })
        self.user_wallet.refresh_from_db()
        other_w.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 350)
        self.assertEqual(other_w.balance, 150)

    def test_077_admin_mass_gold_skips_banned_users(self):
        self.other_role.is_banned = True
        self.other_role.save()
        other_w = Wallet.objects.create(telegram_user_id=self.other_user_id, balance=100)
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'mass_gold',
            'amount': 50
        })
        other_w.refresh_from_db()
        self.assertEqual(other_w.balance, 100) # Intacto por baneo

    def test_078_admin_change_role_to_idol(self):
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'change_role',
            'new_role': 'idol',
            'target_id': self.user_id
        })
        self.user_role.refresh_from_db()
        self.assertEqual(self.user_role.role, 'idol')

    def test_079_admin_toggle_ban_user_to_true(self):
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'toggle_ban',
            'target_id': self.user_id
        })
        self.user_role.refresh_from_db()
        self.assertTrue(self.user_role.is_banned)

    def test_080_admin_toggle_ban_user_to_false(self):
        self.user_role.is_banned = True
        self.user_role.save()
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'toggle_ban',
            'target_id': self.user_id
        })
        self.user_role.refresh_from_db()
        self.assertFalse(self.user_role.is_banned)

    def test_081_admin_reset_single_user_bonus(self):
        self.user_wallet.last_bonus_claim = timezone.now()
        self.user_wallet.save()
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'reset_bonus',
            'target_id': self.user_id
        })
        self.user_wallet.refresh_from_db()
        self.assertIsNone(self.user_wallet.last_bonus_claim)

    def test_082_admin_reset_all_bonuses(self):
        self.user_wallet.last_bonus_claim = timezone.now()
        self.user_wallet.save()
        self.admin_wallet.last_bonus_claim = timezone.now()
        self.admin_wallet.save()
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'reset_all_bonuses'
        })
        self.user_wallet.refresh_from_db()
        self.admin_wallet.refresh_from_db()
        self.assertIsNone(self.user_wallet.last_bonus_claim)
        self.assertIsNone(self.admin_wallet.last_bonus_claim)

    def test_083_admin_broadcast_message_update(self):
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'broadcast_message',
            'broadcast_text': 'Gran Noche de Gala Real',
            'is_active': '1'
        })
        self.assertEqual(KingdomSetting.get_val('broadcast_message'), 'Gran Noche de Gala Real')
        self.assertEqual(KingdomSetting.get_val('broadcast_active'), 'true')

    def test_084_user_role_str_representation(self):
        self.assertIn("123456789", str(self.user_role))
        self.assertIn("cliente", str(self.user_role))

    def test_085_kingdom_setting_get_val_default(self):
        self.assertEqual(KingdomSetting.get_val('non_existent', 'default_val'), 'default_val')

    def test_086_kingdom_setting_set_val(self):
        KingdomSetting.set_val('test_key', 'test_val')
        self.assertEqual(KingdomSetting.get_val('test_key'), 'test_val')

    def test_087_admin_audit_log_creation(self):
        log = AdminAuditLog.objects.create(admin_tg_id=self.admin_id, action="test_action", details="details")
        self.assertIsNotNone(log.created_at)

    def test_088_choose_role_view_get_status_200(self):
        res = self.client.get(f'/choose-role/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_089_choose_role_post_updates_role_to_idol(self):
        self.client.post(reverse('core:choose_role'), {
            'tg_id': self.user_id,
            'role': 'idol'
        })
        self.user_role.refresh_from_db()
        self.assertEqual(self.user_role.role, 'idol')

    def test_090_choose_role_post_updates_role_to_cliente(self):
        self.user_role.role = 'idol'
        self.user_role.save()
        self.client.post(reverse('core:choose_role'), {
            'tg_id': self.user_id,
            'role': 'cliente'
        })
        self.user_role.refresh_from_db()
        self.assertEqual(self.user_role.role, 'cliente')

    def test_091_main_menu_new_user_without_role_redirects_to_choose_role(self):
        res = self.client.get('/?tg_id=777888999')
        self.assertEqual(res.status_code, 302)
        self.assertIn('choose-role', res.url)

    def test_092_main_menu_existing_user_status_200(self):
        res = self.client.get(f'/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_093_main_menu_admin_has_admin_flag(self):
        res = self.client.get(f'/?tg_id={self.admin_id}')
        self.assertTrue(res.context['is_admin'])

    def test_094_main_menu_client_does_not_have_admin_flag(self):
        res = self.client.get(f'/?tg_id={self.user_id}')
        self.assertFalse(res.context['is_admin'])

    def test_095_user_role_choices_vip(self):
        self.user_role.role = 'vip'
        self.user_role.save()
        self.assertEqual(self.user_role.role, 'vip')

    def test_096_user_role_choices_moderador(self):
        self.user_role.role = 'moderador'
        self.user_role.save()
        self.assertEqual(self.user_role.role, 'moderador')

    def test_097_audit_log_tracks_target_user(self):
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'adjust_gold',
            'mode': 'add',
            'amount': 10,
            'target_id': self.user_id
        })
        log = AdminAuditLog.objects.filter(target_tg_id=self.user_id).first()
        self.assertIsNotNone(log)

    def test_098_admin_panel_get_metrics_context(self):
        res = self.client.get(f'/admin-panel/?tg_id={self.admin_id}')
        self.assertIn('total_usuarios', res.context)
        self.assertIn('total_oro', res.context)

    def test_099_admin_adjust_gold_zero_amount(self):
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'adjust_gold',
            'mode': 'add',
            'amount': 0,
            'target_id': self.user_id
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    def test_100_user_role_ban_reason_stored(self):
        self.user_role.is_banned = True
        self.user_role.ban_reason = "Conducta indecorosa"
        self.user_role.save()
        self.user_role.refresh_from_db()
        self.assertEqual(self.user_role.ban_reason, "Conducta indecorosa")

    def test_101_admin_panel_post_invalid_action_ignored(self):
        res = self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {'accion': 'inventada'})
        self.assertEqual(res.status_code, 200)

    def test_102_admin_panel_post_change_role_persisted(self):
        self.client.post(f'/admin-panel/?tg_id={self.admin_id}', {
            'accion': 'change_role',
            'new_role': 'vip',
            'target_id': self.user_id
        })
        self.user_role.refresh_from_db()
        self.assertEqual(self.user_role.role, 'vip')

    def test_103_admin_required_decorator_redirects_no_tg_id(self):
        res = self.client.get('/admin-panel/')
        self.assertEqual(res.status_code, 302)

    def test_104_main_menu_context_has_user_profile(self):
        res = self.client.get(f'/?tg_id={self.user_id}')
        self.assertIn('user_profile', res.context)

    def test_105_main_menu_context_has_role(self):
        res = self.client.get(f'/?tg_id={self.user_id}')
        self.assertEqual(res.context['role'], 'cliente')

    # ==========================================
    # BLOQUE 4: MASCOTAS Y SANTUARIO (106 - 135)
    # ==========================================
    def test_106_adopt_pet_creation(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.assertEqual(pet.level, 1)
        self.assertEqual(pet.energy, 80)
        self.assertEqual(pet.xp, 0)

    def test_107_pet_feed_action_caps_energy_at_100(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther", energy=90)
        pet.feed()
        self.assertEqual(pet.energy, 100)
        self.assertEqual(pet.xp, 30)

    def test_108_pet_pet_action_xp(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        pet.pet_action()
        self.assertEqual(pet.xp, 10)

    def test_109_pet_level_up(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther", xp=90)
        pet.feed()
        self.assertEqual(pet.level, 2)
        self.assertEqual(pet.xp, 20)

    def test_110_pet_buff_description_fox(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="fox")
        self.assertIn("22h", pet.get_buff_description())

    def test_111_pet_buff_description_panther(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.assertIn("+10%", pet.get_buff_description())

    def test_112_pet_buff_description_viper(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="viper")
        self.assertIn("15%", pet.get_buff_description())

    def test_113_pet_buff_description_raven(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="raven")
        self.assertIn("Jackpot", pet.get_buff_description())

    def test_114_pet_buff_description_wolf(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="wolf")
        self.assertIn("Blackjack", pet.get_buff_description())

    def test_115_interact_feed_via_view_deducts_15_gold(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.client.post('/pets/interact/', {'tg_id': self.user_id, 'action': 'feed'})
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 285)

    def test_116_interact_feed_insufficient_gold(self):
        self.user_wallet.balance = 5
        self.user_wallet.save()
        Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.client.post('/pets/interact/', {'tg_id': self.user_id, 'action': 'feed'})
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 5)

    def test_117_interact_pet_action_free(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.client.post('/pets/interact/', {'tg_id': self.user_id, 'action': 'pet'})
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    def test_118_change_pet_transmutation(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.client.post('/pets/change/', {
            'tg_id': self.user_id,
            'new_species': 'fox',
            'new_name': 'Kitsune'
        })
        self.user_wallet.refresh_from_db()
        pet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 0)
        self.assertEqual(pet.name, "Kitsune")
        self.assertEqual(pet.species, "fox")

    def test_119_change_pet_insufficient_gold(self):
        self.user_wallet.balance = 100
        self.user_wallet.save()
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.client.post('/pets/change/', {
            'tg_id': self.user_id,
            'new_species': 'fox',
            'new_name': 'Kitsune'
        })
        pet.refresh_from_db()
        self.assertEqual(pet.species, "panther")

    def test_120_adopt_pet_via_view(self):
        self.client.post(reverse('pets:adopt'), {
            'tg_id': self.user_id,
            'name': 'Fenrir',
            'species': 'wolf'
        })
        pet = Pet.objects.filter(telegram_user_id=self.user_id).first()
        self.assertIsNotNone(pet)
        self.assertEqual(pet.name, 'Fenrir')

    def test_121_adopt_second_pet_rejected(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.client.post(reverse('pets:adopt'), {
            'tg_id': self.user_id,
            'name': 'Fenrir',
            'species': 'wolf'
        })
        self.assertEqual(Pet.objects.filter(telegram_user_id=self.user_id).count(), 1)

    def test_122_pet_sanctuary_get_status_200(self):
        res = self.client.get(f'/pets/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_123_pet_image_url_mapping_fox(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="K", species="fox")
        self.assertEqual(pet.get_image_url(), "/media/pets/fox.png")

    def test_124_pet_image_url_mapping_panther(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="K", species="panther")
        self.assertEqual(pet.get_image_url(), "/media/pets/panther.png")

    def test_125_pet_image_url_mapping_viper(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="K", species="viper")
        self.assertEqual(pet.get_image_url(), "/media/pets/viper.png")

    def test_126_pet_image_url_mapping_raven(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="K", species="raven")
        self.assertEqual(pet.get_image_url(), "/media/pets/raven.png")

    def test_127_pet_image_url_mapping_wolf(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="K", species="wolf")
        self.assertEqual(pet.get_image_url(), "/media/pets/wolf.png")

    def test_128_pet_str_representation(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="Shadow", species="panther")
        self.assertIn("Shadow", str(pet))

    def test_129_pet_xp_to_next_level_scaling(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="K", species="fox", level=3)
        self.assertEqual(pet.xp_to_next_level, 300)

    def test_130_pet_xp_percentage_calculation(self):
        pet = Pet.objects.create(telegram_user_id=self.user_id, name="K", species="fox", level=1, xp=50)
        self.assertEqual(pet.xp_percentage, 50)

    def test_131_pet_unique_owner_constraint(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="K1", species="fox")
        with self.assertRaises(Exception):
            Pet.objects.create(telegram_user_id=self.user_id, name="K2", species="wolf")

    def test_132_pet_change_without_new_name_fails(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.client.post('/pets/change/', {
            'tg_id': self.user_id,
            'new_species': 'fox',
            'new_name': ''
        })
        self.assertEqual(self.user_wallet.balance, 300)

    def test_133_pet_feed_grants_player_xp(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.client.post('/pets/interact/', {'tg_id': self.user_id, 'action': 'feed'})
        self.user_profile.refresh_from_db()
        self.assertGreater(self.user_profile.current_xp, 0)

    def test_134_pet_pet_action_grants_player_xp(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Kuro", species="panther")
        self.client.post('/pets/interact/', {'tg_id': self.user_id, 'action': 'pet'})
        self.user_profile.refresh_from_db()
        self.assertGreater(self.user_profile.current_xp, 0)

    def test_135_pet_adoption_grants_35_player_xp(self):
        self.client.post(reverse('pets:adopt'), {
            'tg_id': self.user_id,
            'name': 'Kitsune',
            'species': 'fox'
        })
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.current_xp, 35)

    # ==========================================
    # BLOQUE 5: IDOLS, ELENCO & FEED (136 - 170)
    # ==========================================
    def test_136_create_idol_profile(self):
        idol = IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="Scarlett", bio="Musa")
        self.assertEqual(idol.rating, 5.00)
        self.assertEqual(idol.services_done, 0)

    def test_137_idol_max_3_limit_validation(self):
        IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="I1", bio="B")
        IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="I2", bio="B")
        third = IdolProfile(telegram_user_id=self.user_id, stage_name="I3", bio="B")
        with self.assertRaises(ValidationError):
            third.clean()

    def test_138_review_recalculates_average(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        Review.objects.create(idol=idol, client_telegram_id=self.user_id, client_username="Alex", rating=4, comment="Ok")
        Review.objects.create(idol=idol, client_telegram_id=self.other_user_id, client_username="Marc", rating=5, comment="Top")
        idol.refresh_from_db()
        self.assertEqual(idol.services_done, 2)
        self.assertEqual(float(idol.rating), 4.50)

    def test_139_post_creation_public(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        p = Post.objects.create(idol=idol, network='gram', caption="Public")
        self.assertEqual(p.price, 0)

    def test_140_post_creation_vip(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        p = Post.objects.create(idol=idol, network='fans', price=75, caption="VIP")
        self.assertEqual(p.price, 75)

    def test_141_unlock_vip_post_financial_split(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        idol_wallet = Wallet.objects.create(telegram_user_id=888, balance=100)
        post = Post.objects.create(idol=idol, network='fans', price=100, caption="VIP")
        self.client.post(reverse('idols:unlock_post', args=[post.id]), {'tg_id': self.user_id})
        self.user_wallet.refresh_from_db()
        idol_wallet.refresh_from_db()
        # 85% para la Idol = +85
        self.assertEqual(idol_wallet.balance, 185)

    def test_142_unlock_vip_post_viper_discount(self):
        Pet.objects.create(telegram_user_id=self.user_id, name="Sly", species="viper")
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        Wallet.objects.create(telegram_user_id=888, balance=100)
        post = Post.objects.create(idol=idol, network='fans', price=100, caption="VIP")
        self.client.post(reverse('idols:unlock_post', args=[post.id]), {'tg_id': self.user_id})
        self.user_wallet.refresh_from_db()
        # Con víbora: 100 * 0.85 = 85 cobrados -> 300 - 85 = 215 exactos
        self.assertEqual(self.user_wallet.balance, 215)

    def test_143_prevent_double_unlock_same_post(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        post = Post.objects.create(idol=idol, network='fans', price=50, caption="VIP")
        PostUnlock.objects.create(post=post, client_telegram_id=self.user_id)
        with self.assertRaises(Exception):
            PostUnlock.objects.create(post=post, client_telegram_id=self.user_id)

    def test_144_insufficient_funds_blocks_vip_unlock(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        post = Post.objects.create(idol=idol, network='fans', price=500, caption="VIP Caro")
        self.client.post(reverse('idols:unlock_post', args=[post.id]), {'tg_id': self.user_id})
        self.assertFalse(PostUnlock.objects.filter(post=post, client_telegram_id=self.user_id).exists())

    def test_145_post_like_toggle_on_and_off(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        post = Post.objects.create(idol=idol, network='gram', caption="Foto")
        res1 = self.client.post(reverse('idols:toggle_like', args=[post.id]), {'tg_id': self.user_id})
        self.assertTrue(res1.json()['liked'])
        res2 = self.client.post(reverse('idols:toggle_like', args=[post.id]), {'tg_id': self.user_id})
        self.assertFalse(res2.json()['liked'])

    def test_146_send_tip_to_idol(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        idol_wallet = Wallet.objects.create(telegram_user_id=888, balance=50)
        post = Post.objects.create(idol=idol, network='gram', caption="Foto")
        self.client.post(reverse('idols:send_tip', args=[post.id]), {'tg_id': self.user_id, 'tip_amount': 50})
        self.user_wallet.refresh_from_db()
        idol_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 250)
        self.assertEqual(idol_wallet.balance, 95) # 50 - 5 = 45 neto

    def test_147_custom_request_held_in_custody(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        self.client.post(reverse('idols:create_custom_request', args=[idol.id]), {
            'tg_id': self.user_id,
            'bounty': 100,
            'description': 'Foto en vestido'
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 200)

    def test_148_custom_request_rejected_refunds_client(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        req = CustomRequest.objects.create(
            idol=idol, client_telegram_id=self.user_id, client_username="Alex",
            description="Antojo", bounty=100, status='pending'
        )
        self.client.post(reverse('idols:list'), {'tg_id': 888, 'action': 'reject_request', 'request_id': req.id})
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 400)

    def test_149_post_comment_creation(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        post = Post.objects.create(idol=idol, network='gram', caption="Foto")
        self.client.post(reverse('idols:add_comment', args=[post.id]), {
            'tg_id': self.user_id,
            'tg_username': 'LordAlex',
            'text': 'Radiante'
        })
        comment = PostComment.objects.filter(post=post).first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.text, 'Radiante')

    def test_150_idol_gallery_status_200(self):
        res = self.client.get(f'/idols/gallery/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_151_idol_detail_status_200(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        res = self.client.get(f'/idols/{idol.id}/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_152_social_feed_status_200(self):
        res = self.client.get(f'/idols/feed/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_153_collection_view_status_200(self):
        res = self.client.get(f'/idols/collection/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_154_idol_update_status_to_antojos(self):
        idol = IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="S", bio="B")
        self.client.post(reverse('idols:list'), {
            'tg_id': self.user_id,
            'action': 'update_status',
            'idol_id': idol.id,
            'status': 'antojos'
        })
        idol.refresh_from_db()
        self.assertEqual(idol.status, 'antojos')

    def test_155_idol_update_status_to_offline(self):
        idol = IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="S", bio="B")
        self.client.post(reverse('idols:list'), {
            'tg_id': self.user_id,
            'action': 'update_status',
            'idol_id': idol.id,
            'status': 'offline'
        })
        idol.refresh_from_db()
        self.assertEqual(idol.status, 'offline')

    def test_156_idol_cannot_review_own_profile(self):
        idol = IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="S", bio="B")
        self.client.post(reverse('idols:detail', args=[idol.id]), {
            'tg_id': self.user_id,
            'rating': 5,
            'comment': 'Auto elogio'
        })
        self.assertEqual(Review.objects.filter(idol=idol).count(), 0)

    def test_157_idol_delete_action(self):
        idol = IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="S", bio="B")
        self.client.post(reverse('idols:delete', args=[idol.id]), {'tg_id': self.user_id})
        self.assertFalse(IdolProfile.objects.filter(id=idol.id).exists())

    def test_158_send_tip_to_self_blocked(self):
        idol = IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="S", bio="B")
        post = Post.objects.create(idol=idol, network='gram', caption="Foto")
        self.client.post(reverse('idols:send_tip', args=[post.id]), {'tg_id': self.user_id, 'tip_amount': 50})
        self.assertEqual(self.user_wallet.balance, 300)

    def test_159_idol_aura_choices_stored(self):
        idol = IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="S", bio="B", aura_color="gold")
        self.assertEqual(idol.aura_color, "gold")

    def test_160_idol_tagline_stored(self):
        idol = IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="S", bio="B", tagline="La Reina")
        self.assertEqual(idol.tagline, "La Reina")

    def test_161_idol_specialty_stored(self):
        idol = IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="S", bio="B", specialty="Romántico")
        self.assertEqual(idol.specialty, "Romántico")

    def test_162_idol_welcome_message_stored(self):
        idol = IdolProfile.objects.create(telegram_user_id=self.user_id, stage_name="S", bio="B", welcome_message="Hola noble")
        self.assertEqual(idol.welcome_message, "Hola noble")

    def test_163_post_likes_default_zero(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        post = Post.objects.create(idol=idol, network='gram', caption="Foto")
        self.assertEqual(post.likes, 0)

    def test_164_post_unlock_records_client_id(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        post = Post.objects.create(idol=idol, network='fans', price=10, caption="VIP")
        unlock = PostUnlock.objects.create(post=post, client_telegram_id=self.user_id)
        self.assertEqual(unlock.client_telegram_id, self.user_id)

    def test_165_collection_displays_only_unlocked_posts(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        p1 = Post.objects.create(idol=idol, network='fans', price=10, caption="VIP 1")
        p2 = Post.objects.create(idol=idol, network='fans', price=10, caption="VIP 2")
        PostUnlock.objects.create(post=p1, client_telegram_id=self.user_id)
        res = self.client.get(f'/idols/collection/?tg_id={self.user_id}')
        self.assertEqual(len(res.context['posts']), 1)

    def test_166_review_requires_rating_between_1_and_5(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        self.client.post(reverse('idols:detail', args=[idol.id]), {'tg_id': self.user_id, 'rating': 10, 'comment': 'X'})
        self.assertEqual(Review.objects.filter(idol=idol).count(), 0)

    def test_167_review_requires_non_empty_comment(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        self.client.post(reverse('idols:detail', args=[idol.id]), {'tg_id': self.user_id, 'rating': 5, 'comment': ''})
        self.assertEqual(Review.objects.filter(idol=idol).count(), 0)

    def test_168_custom_request_requires_description(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        self.client.post(reverse('idols:create_custom_request', args=[idol.id]), {
            'tg_id': self.user_id,
            'bounty': 100,
            'description': ''
        })
        self.assertEqual(CustomRequest.objects.filter(idol=idol).count(), 0)

    def test_169_post_str_representation(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        post = Post.objects.create(idol=idol, network='gram', caption="Foto")
        self.assertIn("Elena", str(post))

    def test_170_idol_str_representation(self):
        idol = IdolProfile.objects.create(telegram_user_id=888, stage_name="Elena", bio="B")
        self.assertIn("Elena", str(idol))

    # ==========================================
    # BLOQUE 6: CASINO & JUEGOS IMPERIALES (171 - 200)
    # ==========================================
    def test_171_casino_roulette_bet_cap_at_100(self):
        self.client.post(reverse('economy:casino'), {
            'tg_id': self.user_id,
            'bet_amount': 150,
            'bet_choice': 'red'
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    def test_172_casino_roulette_negative_bet_rejected(self):
        self.client.post(reverse('economy:casino'), {
            'tg_id': self.user_id,
            'bet_amount': -20,
            'bet_choice': 'red'
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    def test_173_casino_roulette_zero_bet_rejected(self):
        self.client.post(reverse('economy:casino'), {
            'tg_id': self.user_id,
            'bet_amount': 0,
            'bet_choice': 'red'
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    def test_174_casino_roulette_bet_exceeds_balance_rejected(self):
        self.user_wallet.balance = 20
        self.user_wallet.save()
        self.client.post(reverse('economy:casino'), {
            'tg_id': self.user_id,
            'bet_amount': 50,
            'bet_choice': 'red'
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 20)

    def test_175_slots_bet_cap_at_100(self):
        self.client.post(reverse('economy:slots'), {
            'tg_id': self.user_id,
            'bet_amount': 150
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    def test_176_slots_negative_bet_rejected(self):
        self.client.post(reverse('economy:slots'), {
            'tg_id': self.user_id,
            'bet_amount': -10
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    def test_177_slots_bet_exceeds_balance_rejected(self):
        self.user_wallet.balance = 10
        self.user_wallet.save()
        self.client.post(reverse('economy:slots'), {
            'tg_id': self.user_id,
            'bet_amount': 50
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 10)

    def test_178_blackjack_deal_deducts_bet(self):
        res = self.client.post(reverse('economy:blackjack'), {
            'tg_id': self.user_id,
            'action': 'deal',
            'bet_amount': 25
        })
        self.user_wallet.refresh_from_db()
        # Puede restar 25 de la apuesta (275) o ganar de inmediato con Blackjack Natural x2.5 (337)
        self.assertTrue(self.user_wallet.balance <= 275 or self.user_wallet.balance == 337)

    def test_179_blackjack_deal_invalid_bet_blocked(self):
        self.client.post(reverse('economy:blackjack'), {
            'tg_id': self.user_id,
            'action': 'deal',
            'bet_amount': 150
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    def test_180_blackjack_deal_zero_bet_blocked(self):
        self.client.post(reverse('economy:blackjack'), {
            'tg_id': self.user_id,
            'action': 'deal',
            'bet_amount': 0
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 300)

    def test_181_blackjack_deal_exceeds_balance_blocked(self):
        self.user_wallet.balance = 10
        self.user_wallet.save()
        self.client.post(reverse('economy:blackjack'), {
            'tg_id': self.user_id,
            'action': 'deal',
            'bet_amount': 25
        })
        self.user_wallet.refresh_from_db()
        self.assertEqual(self.user_wallet.balance, 10)

    def test_182_casino_view_get_status_200(self):
        res = self.client.get(f'/economy/casino/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_183_slots_view_get_status_200(self):
        res = self.client.get(f'/economy/slots/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_184_blackjack_view_get_status_200(self):
        res = self.client.get(f'/economy/blackjack/?tg_id={self.user_id}')
        self.assertEqual(res.status_code, 200)

    def test_185_claim_daily_bonus_flow(self):
        init_balance = self.user_wallet.balance
        self.client.post(reverse('economy:claim_bonus'), {'tg_id': self.user_id})
        self.user_wallet.refresh_from_db()
        self.user_profile.refresh_from_db()
        self.assertGreater(self.user_wallet.balance, init_balance)
        self.assertEqual(self.user_profile.current_xp, 45)
        self.assertFalse(self.user_wallet.can_claim_bonus())

    def test_186_blackjack_hand_value_aces_soft(self):
        from economy.views import calculate_hand_value
        hand = [{'val': 'A'}, {'val': '5'}]
        self.assertEqual(calculate_hand_value(hand), 16)

    def test_187_blackjack_hand_value_aces_hard(self):
        from economy.views import calculate_hand_value
        hand = [{'val': 'A'}, {'val': '10'}, {'val': '5'}]
        self.assertEqual(calculate_hand_value(hand), 16) # 11 + 10 + 5 = 26 > 21 -> 1 + 10 + 5 = 16

    def test_188_blackjack_hand_value_face_cards(self):
        from economy.views import calculate_hand_value
        hand = [{'val': 'J'}, {'val': 'Q'}, {'val': 'K'}]
        self.assertEqual(calculate_hand_value(hand), 30)

    def test_189_blackjack_draw_card_structure(self):
        from economy.views import draw_card
        card = draw_card()
        self.assertIn('val', card)
        self.assertIn('suit', card)
        self.assertIn('is_red', card)

    def test_190_casino_roulette_bet_red_valid(self):
        res = self.client.post(reverse('economy:casino'), {
            'tg_id': self.user_id,
            'bet_amount': 10,
            'bet_choice': 'red'
        })
        self.assertEqual(res.status_code, 200)

    def test_191_casino_roulette_bet_black_valid(self):
        res = self.client.post(reverse('economy:casino'), {
            'tg_id': self.user_id,
            'bet_amount': 10,
            'bet_choice': 'black'
        })
        self.assertEqual(res.status_code, 200)

    def test_192_casino_roulette_bet_zero_valid(self):
        res = self.client.post(reverse('economy:casino'), {
            'tg_id': self.user_id,
            'bet_amount': 10,
            'bet_choice': 'zero'
        })
        self.assertEqual(res.status_code, 200)

    def test_193_slots_spin_valid_deducts_or_pays(self):
        res = self.client.post(reverse('economy:slots'), {
            'tg_id': self.user_id,
            'bet_amount': 10
        })
        self.assertEqual(res.status_code, 200)
        self.user_wallet.refresh_from_db()
        self.assertNotEqual(self.user_wallet.balance, 300)

    def test_194_blackjack_hit_action_without_deal_ignored(self):
        res = self.client.post(reverse('economy:blackjack'), {
            'tg_id': self.user_id,
            'action': 'hit'
        })
        self.assertEqual(res.status_code, 200)

    def test_195_blackjack_stand_action_without_deal_ignored(self):
        res = self.client.post(reverse('economy:blackjack'), {
            'tg_id': self.user_id,
            'action': 'stand'
        })
        self.assertEqual(res.status_code, 200)

    def test_196_profile_badge_high_roller(self):
        self.user_profile.vip_badge = 'high_roller'
        self.user_profile.save()
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.vip_badge, 'high_roller')

    def test_197_profile_badge_mecenas(self):
        self.user_profile.vip_badge = 'mecenas'
        self.user_profile.save()
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.vip_badge, 'mecenas')

    def test_198_profile_badge_coleccionista(self):
        self.user_profile.vip_badge = 'coleccionista'
        self.user_profile.save()
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.vip_badge, 'coleccionista')

    def test_199_profile_badge_romantico(self):
        self.user_profile.vip_badge = 'romantico'
        self.user_profile.save()
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.vip_badge, 'romantico')

    def test_200_grand_master_final_integrity_check(self):
        # Valida que todos los subsistemas del Kingdom operen al unísono
        self.assertEqual(UserRole.objects.count(), 3)
        self.assertEqual(Wallet.objects.count(), 2)
        self.assertEqual(UserProfile.objects.count(), 1)
        self.assertEqual(self.user_wallet.balance, 300)
        self.assertEqual(self.user_profile.level, 1)