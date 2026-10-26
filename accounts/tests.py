import io
import tempfile
from django import forms
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from digital_wardrobe.models import ClothingItem
from items_for_swap.models import ItemForSwap

from .forms import (
    RegisterForm,
    normalize_phone,
    validate_phone,
    validate_profile_picture,
)
from .models import UserProfile


def make_image_bytes(fmt="PNG", size=(32, 32), color=(175, 63, 95)):
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    img.save(buf, format=fmt)
    return buf.getvalue()


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class Phase1FormFoundationTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="alice", password="Password123!")
        self.profile1 = UserProfile.for_user(self.user1)
        self.profile1.phone_number = "081234567890"
        self.profile1.domicile = "Depok"
        self.profile1.save()

    def test_normalize_phone_converts_plus62_and_62_and_strips_punctuation(self):
        self.assertEqual(normalize_phone("+62 812-3456-7890"), "081234567890")
        self.assertEqual(normalize_phone("6281234567890"), "081234567890")
        self.assertEqual(normalize_phone("0812 3456 7890"), "081234567890")

    def test_validate_phone_rejects_duplicate_from_other_user(self):
        with self.assertRaisesMessage(forms.ValidationError, "Nomor HP ini sudah dipakai akun lain."):
            validate_phone("+6281234567890")

    def test_validate_phone_allows_own_phone_when_exclude_profile_provided(self):
        cleaned = validate_phone("+62 812-3456-7890", exclude_profile=self.profile1)
        self.assertEqual(cleaned, "081234567890")

    def test_validate_phone_rejects_invalid_format(self):
        with self.assertRaisesMessage(forms.ValidationError, "Masukkan nomor HP yang valid"):
            validate_phone("12345")

    def test_register_form_regression_normalizes_and_checks_duplicate(self):
        dup_form = RegisterForm(data={
            "username": "bob",
            "phone_number": "+6281234567890",
            "domicile": "Jakarta",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        self.assertFalse(dup_form.is_valid())
        self.assertIn("phone_number", dup_form.errors)

        ok_form = RegisterForm(data={
            "username": "bob",
            "phone_number": "+62 813-9999-8888",
            "domicile": "Bandung",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        self.assertTrue(ok_form.is_valid(), ok_form.errors)
        user = ok_form.save()
        profile = UserProfile.for_user(user)
        self.assertEqual(profile.phone_number, "081399998888")
        self.assertEqual(profile.domicile, "Bandung")

    def test_validate_profile_picture_accepts_valid_png_and_jpeg(self):
        png_file = SimpleUploadedFile("avatar.png", make_image_bytes("PNG"), content_type="image/png")
        jpg_file = SimpleUploadedFile("avatar.jpg", make_image_bytes("JPEG"), content_type="image/jpeg")
        self.assertEqual(validate_profile_picture(png_file), png_file)
        self.assertEqual(validate_profile_picture(jpg_file), jpg_file)

    def test_validate_profile_picture_rejects_oversized_or_fake_image(self):
        big_file = SimpleUploadedFile("big.png", b"x" * (5 * 1024 * 1024 + 10), content_type="image/png")
        with self.assertRaisesMessage(forms.ValidationError, "Ukuran foto maksimal 5 MB."):
            validate_profile_picture(big_file)

        fake_jpg = SimpleUploadedFile("fake.jpg", b"not-an-image-at-all", content_type="image/jpeg")
        with self.assertRaisesMessage(forms.ValidationError, "Foto harus berformat JPG atau PNG."):
            validate_profile_picture(fake_jpg)

        gif_file = SimpleUploadedFile("anim.gif", make_image_bytes("GIF"), content_type="image/gif")
        with self.assertRaisesMessage(forms.ValidationError, "Foto harus berformat JPG atau PNG."):
            validate_profile_picture(gif_file)


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class Phase2MyProfileAndNavbarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="iqbal", password="Password123!")
        self.profile = UserProfile.for_user(self.user)
        self.profile.display_name = "Iqbal V"
        self.profile.phone_number = "081298765432"
        self.profile.domicile = "Depok"
        self.profile.bio = "Suka gaya streetwear dan minimalist."
        self.profile.preferred_styles = ["streetwear", "minimalist"]
        self.profile.preferred_clothing_sizes = ["M", "L"]
        self.profile.preferred_shoe_sizes = [42]
        self.profile.onboarding_completed = True
        self.profile.save()

    def _create_clothing_item(self, name, listed=False):
        img = SimpleUploadedFile(f"{name}.png", make_image_bytes("PNG"), content_type="image/png")
        return ClothingItem.objects.create(
            user=self.user,
            name=name,
            category="top",
            size="M",
            gender="unisex",
            condition="good",
            color="neutral",
            image=img,
            is_listed_for_swap=listed,
        )

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_profile_displays_user_details_and_accurate_counts(self):
        self._create_clothing_item("Kemeja Flanel", listed=False)
        self._create_clothing_item("Jaket Denim", listed=False)
        self._create_clothing_item("Kaos Hitam", listed=True)

        self.client.login(username="iqbal", password="Password123!")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["wardrobe_count"], 2)
        self.assertEqual(response.context["swap_count"], 1)

        content = response.content.decode("utf-8")
        self.assertIn("Iqbal V", content)
        self.assertIn("@iqbal", content)
        self.assertIn("Depok", content)
        self.assertIn("Suka gaya streetwear dan minimalist.", content)
        self.assertIn("Streetwear", content)
        self.assertIn("Minimalist", content)
        self.assertIn("EU 42", content)
        self.assertIn("081298765432", content)

    def test_navbar_has_active_profile_link_and_no_segera_hadir_badge(self):
        self.client.login(username="iqbal", password="Password123!")
        response = self.client.get(reverse("accounts:profile"))
        content = response.content.decode("utf-8")
        self.assertIn(f'href="{reverse("accounts:profile")}"', content)
        self.assertNotIn("segera hadir", content)


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class Phase3EditProfileTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="iqbal", password="Password123!")
        self.profile1 = UserProfile.for_user(self.user1)
        self.profile1.display_name = "Iqbal"
        self.profile1.phone_number = "081211112222"
        self.profile1.domicile = "Depok"
        self.profile1.save()

        self.user2 = User.objects.create_user(username="fanny", password="Password123!")
        self.profile2 = UserProfile.for_user(self.user2)
        self.profile2.phone_number = "081233334444"
        self.profile2.domicile = "Jakarta"
        self.profile2.save()

    def test_edit_profile_requires_login(self):
        response = self.client.get(reverse("accounts:edit_profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_edit_profile_updates_all_fields_and_allows_own_phone_with_plus62(self):
        self.client.login(username="iqbal", password="Password123!")
        avatar = SimpleUploadedFile("new_avatar.png", make_image_bytes("PNG"), content_type="image/png")
        response = self.client.post(
            reverse("accounts:edit_profile"),
            data={
                "display_name": "Iqbal Baru",
                "phone_number": "+62 812-1111-2222",
                "domicile": "Bandung",
                "bio": "Kolektor jaket vintage.",
                "preferred_styles": ["vintage", "streetwear"],
                "preferred_clothing_sizes": ["L", "XL"],
                "preferred_shoe_sizes": ["41", "42"],
                "profile_picture": avatar,
            },
            follow=True,
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        self.assertContains(response, "Profil berhasil diperbarui.")

        self.profile1.refresh_from_db()
        self.assertEqual(self.profile1.display_name, "Iqbal Baru")
        self.assertEqual(self.profile1.phone_number, "081211112222")
        self.assertEqual(self.profile1.domicile, "Bandung")
        self.assertEqual(self.profile1.bio, "Kolektor jaket vintage.")
        self.assertEqual(self.profile1.preferred_styles, ["vintage", "streetwear"])
        self.assertEqual(self.profile1.preferred_clothing_sizes, ["L", "XL"])
        self.assertEqual(self.profile1.preferred_shoe_sizes, [41, 42])
        self.assertTrue(bool(self.profile1.profile_picture))

    def test_edit_profile_rejects_other_users_phone_number(self):
        self.client.login(username="iqbal", password="Password123!")
        response = self.client.post(
            reverse("accounts:edit_profile"),
            data={
                "display_name": "Iqbal",
                "phone_number": "+6281233334444",
                "domicile": "Depok",
                "bio": "Halo",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nomor HP ini sudah dipakai akun lain.")
        self.profile1.refresh_from_db()
        self.assertEqual(self.profile1.phone_number, "081211112222")

    def test_edit_profile_rejects_bio_over_300_chars_and_invalid_image(self):
        self.client.login(username="iqbal", password="Password123!")
        fake_img = SimpleUploadedFile("fake.png", b"not-an-image", content_type="image/png")
        response = self.client.post(
            reverse("accounts:edit_profile"),
            data={
                "display_name": "Iqbal",
                "phone_number": "081211112222",
                "domicile": "Depok",
                "bio": "a" * 305,
                "profile_picture": fake_img,
            },
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("bio", form.errors)
        self.assertIn("profile_picture", form.errors)


class Phase4ChangePasswordTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="iqbal", password="OldPassword123!")
        UserProfile.for_user(self.user)

    def test_change_password_requires_login(self):
        response = self.client.get(reverse("accounts:change_password"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_change_password_success_keeps_user_logged_in(self):
        self.client.login(username="iqbal", password="OldPassword123!")
        response = self.client.post(
            reverse("accounts:change_password"),
            data={
                "old_password": "OldPassword123!",
                "new_password1": "NewStrongPass456!",
                "new_password2": "NewStrongPass456!",
            },
            follow=True,
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        self.assertContains(response, "Password berhasil diganti.")
        # Pastikan session tetap aktif (tidak ter-logout)
        profile_res = self.client.get(reverse("accounts:profile"))
        self.assertEqual(profile_res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrongPass456!"))

    def test_change_password_rejects_wrong_old_password_or_mismatch(self):
        self.client.login(username="iqbal", password="OldPassword123!")
        res_wrong_old = self.client.post(
            reverse("accounts:change_password"),
            data={
                "old_password": "WrongOldPassword!",
                "new_password1": "NewStrongPass456!",
                "new_password2": "NewStrongPass456!",
            },
        )
        self.assertEqual(res_wrong_old.status_code, 200)
        self.assertIn("old_password", res_wrong_old.context["form"].errors)

        res_mismatch = self.client.post(
            reverse("accounts:change_password"),
            data={
                "old_password": "OldPassword123!",
                "new_password1": "NewStrongPass456!",
                "new_password2": "DifferentPass789!",
            },
        )
        self.assertEqual(res_mismatch.status_code, 200)
        self.assertIn("new_password2", res_mismatch.context["form"].errors)


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class Phase5PublicProfileTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(username="iqbal", password="Password123!")
        UserProfile.for_user(self.viewer)

        self.owner = User.objects.create_user(username="fanny", password="Password123!")
        self.owner_profile = UserProfile.for_user(self.owner)
        self.owner_profile.display_name = "Fanny"
        self.owner_profile.phone_number = "081299990000"
        self.owner_profile.domicile = "Bandung"
        self.owner_profile.bio = "Pencinta linen dan warna bumi."
        self.owner_profile.preferred_styles = ["korean", "casual"]
        self.owner_profile.preferred_clothing_sizes = ["S", "M"]
        self.owner_profile.preferred_shoe_sizes = [38]
        self.owner_profile.save()

    def _create_item(self, user, name, listed=False, deleted=False):
        img = SimpleUploadedFile(f"{name}.png", make_image_bytes("PNG"), content_type="image/png")
        return ClothingItem.objects.create(
            user=user,
            name=name,
            category="top",
            size="M",
            gender="unisex",
            condition="good",
            color="neutral",
            image=img,
            is_listed_for_swap=listed,
            deleted_at=timezone.now() if deleted else None,
        )

    def test_public_profile_requires_login(self):
        url = reverse("accounts:public_profile", kwargs={"username": "fanny"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_public_profile_returns_404_for_unknown_or_inactive_user(self):
        self.client.login(username="iqbal", password="Password123!")
        res_unknown = self.client.get(reverse("accounts:public_profile", kwargs={"username": "tidak_ada"}))
        self.assertEqual(res_unknown.status_code, 404)

        inactive = User.objects.create_user(username="nonaktif", password="Password123!", is_active=False)
        UserProfile.for_user(inactive)
        res_inactive = self.client.get(reverse("accounts:public_profile", kwargs={"username": "nonaktif"}))
        self.assertEqual(res_inactive.status_code, 404)

    def test_public_profile_displays_public_info_and_never_exposes_phone_number(self):
        self.client.login(username="iqbal", password="Password123!")
        url = reverse("accounts:public_profile", kwargs={"username": "fanny"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fanny")
        self.assertContains(response, "@fanny")
        self.assertContains(response, "Bandung")
        self.assertContains(response, "Pencinta linen dan warna bumi.")
        self.assertContains(response, "Korean")
        self.assertContains(response, "EU 38")
        # Nomor HP TIDAK BOLEH bocor di profil publik
        self.assertNotContains(response, "081299990000")

        # Bahkan saat dilihat oleh pemiliknya sendiri melalui URL profil publik
        self.client.login(username="fanny", password="Password123!")
        own_public_res = self.client.get(url)
        self.assertEqual(own_public_res.status_code, 200)
        self.assertNotContains(own_public_res, "081299990000")

    def test_public_profile_shows_only_available_active_swap_listings(self):
        # 1) Listing aktif (Available) -> tampil
        item_active = self._create_item(self.owner, "Kemeja Linen Putih", listed=True)
        ItemForSwap.objects.create(
            clothing_item=item_active,
            user=self.owner,
            meeting_location="Bandung",
            status=ItemForSwap.AVAILABLE,
        )

        # 2) Listing sudah Swapped -> tidak tampil
        item_swapped = self._create_item(self.owner, "Celana Jeans Lama", listed=False)
        ItemForSwap.objects.create(
            clothing_item=item_swapped,
            user=self.owner,
            meeting_location="Bandung",
            status=ItemForSwap.SWAPPED,
        )

        # 3) Item soft-deleted walaupun punya listing available -> tidak tampil
        item_deleted = self._create_item(self.owner, "Jaket Dihapus", listed=True, deleted=True)
        ItemForSwap.objects.create(
            clothing_item=item_deleted,
            user=self.owner,
            meeting_location="Bandung",
            status=ItemForSwap.AVAILABLE,
        )

        # 4) Item pribadi di lemari (is_listed_for_swap=False) -> tidak tampil
        self._create_item(self.owner, "Dress Pribadi", listed=False)

        self.client.login(username="iqbal", password="Password123!")
        response = self.client.get(reverse("accounts:public_profile", kwargs={"username": "fanny"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kemeja Linen Putih")
        self.assertNotContains(response, "Celana Jeans Lama")
        self.assertNotContains(response, "Jaket Dihapus")
        self.assertNotContains(response, "Dress Pribadi")
