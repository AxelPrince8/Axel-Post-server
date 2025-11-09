from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

# Apne Facebook ke cookies ko browser me load karna padega iske liye code ban sakta hai
# Yahan bas simple example diya ja raha hai jo directly logged-in browser ko use karta hai

driver = webdriver.Chrome()  # Chromedriver path configured hona chahiye

# Facebook post URL jahan comment karna hai
post_url = "https://www.facebook.com/permalink.php?story_fbid=POST_ID&id=USER_ID"

driver.get(post_url)

time.sleep(5)  # Page load hone do

# Comment box dhundho (Facebook dynamic hai, xpath update karna par sakta hai)
comment_box = driver.find_element(By.XPATH, "//div[@aria-label='Write a comment']")

comment_box.click()
comment_box.send_keys("Yeh hai mera automatic comment!")
comment_box.send_keys(Keys.RETURN)

time.sleep(5)  # Comment post hone do
driver.quit()
