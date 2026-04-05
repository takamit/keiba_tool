import re
from typing import List

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from utils.logger import get_logger

logger = get_logger()


class RaceListScraper:
    def get_race_ids(self, date: str) -> List[str]:
        url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date}"
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")

        driver = webdriver.Chrome(options=options)
        try:
            driver.get(url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='race_id=']"))
            )
            html = driver.execute_script("return document.documentElement.outerHTML;")
            race_ids = sorted(set(re.findall(r"race_id=(\d{12})", html)))
            logger.info("race_id取得件数: %s", len(race_ids))
            return race_ids
        finally:
            driver.quit()
