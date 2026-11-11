"""個資遮蔽單元測試。所有資料皆為虛構。"""

import unittest

from review_crew.redaction import redact


class RedactNameTests(unittest.TestCase):
    def test_label_name_is_replaced_everywhere(self):
        text = "姓名：王小明\n自傳：我是王小明，熱愛後端開發。"
        result = redact(text)
        self.assertNotIn("王小明", result.text)
        self.assertEqual(result.text.count("[候選人]"), 2)
        self.assertEqual(result.counts["姓名"], 2)

    def test_label_name_stops_at_whitespace(self):
        result = redact("姓名：王小明 電話：0912-345-678")
        self.assertIn("[候選人] 電話：[電話]", result.text)

    def test_user_supplied_names_and_english_name(self):
        text = "Name: Daming Wang\nContact Xiaoming Lee for reference."
        result = redact(text, names="Xiaoming Lee")
        self.assertNotIn("Daming Wang", result.text)
        self.assertNotIn("Xiaoming Lee", result.text)

    def test_custom_label(self):
        result = redact("姓名：陳小華", candidate_label="[候選人A]")
        self.assertEqual(result.text, "姓名：[候選人A]")


class RedactContactTests(unittest.TestCase):
    def test_email(self):
        result = redact("聯絡：test.user+cv@example.com")
        self.assertEqual(result.text, "聯絡：[Email]")

    def test_mobile_formats(self):
        for phone in ("0912-345-678", "0912345678", "0912 345 678", "+886-912-345-678", "+886912345678"):
            with self.subTest(phone=phone):
                self.assertEqual(redact(f"手機{phone}").text, "手機[電話]")

    def test_landline(self):
        self.assertEqual(redact("市話 02-2345-6789").text, "市話 [電話]")
        self.assertEqual(redact("市話 (02)2345-6789#123").text, "市話 [電話]")

    def test_profile_links(self):
        result = redact("作品 https://github.com/someone 與 linkedin.com/in/someone")
        self.assertEqual(result.text, "作品 [個人連結] 與 [個人連結]")


class RedactIdentityTests(unittest.TestCase):
    def test_national_id_next_to_chinese(self):
        # 中文字後面緊接身分證字號，\b 會失效，需正確遮蔽
        self.assertEqual(redact("身分證A123456789").text, "身分證[身分證]")

    def test_birthday_formats(self):
        for value in ("生日：1990/05/20", "出生日期: 民國79年5月20日", "Birthday: 1990-05-20"):
            with self.subTest(value=value):
                self.assertEqual(redact(value).text, "生日：[生日]")

    def test_full_address_keeps_city(self):
        result = redact("住址：台北市中正區測試路一段100號5樓")
        self.assertEqual(result.text, "住址：台北市[地址]")
        self.assertEqual(result.counts["地址"], 1)

    def test_city_only_is_kept(self):
        self.assertEqual(redact("居住地：新北市").text, "居住地：新北市")


class RedactPreservationTests(unittest.TestCase):
    """評估需要的資訊不可被誤遮。"""

    def test_year_month_periods_are_kept(self):
        text = "2019/03 - 2021/05 擔任後端工程師"
        self.assertEqual(redact(text).text, text)

    def test_numbers_and_skills_are_kept(self):
        text = "5 年 Python 經驗，管理 12 人團隊，QPS 提升 30%"
        result = redact(text)
        self.assertEqual(result.text, text)
        self.assertEqual(result.total, 0)

    def test_extra_terms_are_masked(self):
        result = redact("曾任職範例科技，畢業於範例大學", extra_terms="範例科技、範例大學")
        self.assertEqual(result.text, "曾任職[已遮蔽]，畢業於[已遮蔽]")
        self.assertEqual(result.counts["自訂詞"], 2)

    def test_empty_input(self):
        result = redact("")
        self.assertEqual(result.text, "")
        self.assertEqual(result.total, 0)


class RedactResultTests(unittest.TestCase):
    def test_counts_do_not_contain_original_values(self):
        result = redact("姓名：王小明\nEmail: wang@example.com\n手機 0912-345-678")
        joined = " ".join(f"{k}{v}" for k, v in result.counts.items())
        for secret in ("王小明", "wang@example.com", "0912"):
            self.assertNotIn(secret, joined)
        self.assertEqual(result.total, 3)


if __name__ == "__main__":
    unittest.main()
