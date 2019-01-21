import config
import glob
import time
import os
import multiprocessing

from multiprocessing import current_process
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class Worker(multiprocessing.Process):
    def __init__(self, base_download_path: str, timeout: int, queue: multiprocessing.JoinableQueue):
        """
        """
        multiprocessing.Process.__init__(self)
        self.base_download_path = base_download_path
        self.timeout = timeout
        self.queue = queue
        self.stop_event = multiprocessing.Event()
        self.is_loggedin = False

    def stop(self):
        """
        """
        self.stop_event.set()

    def run(self):
        """
        """

        #TODO implement logging in one time only
        #TODO implement moving files to new folder with ticker name
        while not self.stop_event.is_set():
            if not self.queue.empty():
                ticker = self.queue.get()
    
                # execute search and download
                self.__search(ticker)
            else:
                self.stop()

    def __search(self, ticker: str):
        """
        """
        print("[{0}] is searching for {1}".format(current_process().name, ticker))
        
        #set up chrome optins to download files
        options = webdriver.ChromeOptions()
        options.add_experimental_option(
            "prefs", {
                "plugins.plugins_list": [
                    {"enabled":False,"name":"Chrome PDF Viewer"}
                ],
                "download.default_directory": self.base_download_path,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            })

        # instantiate driver and navigate to login page
        driver = webdriver.Chrome(chrome_options=options)
        driver.get(config.LOGIN_URL)
            
        #enter credentials and submit form
        driver.find_element_by_name("user").send_keys(config.LOGIN_NUMBER)
        driver.find_element_by_name("pin").send_keys(config.LOGIN_PIN)
        driver.find_element_by_tag_name("form").submit()

        try:
            # wait maximum 20 seconds for SSO login/redirect to occur
            #TODO catch timeout exception
            WebDriverWait(driver, self.timeout).until(
                EC.title_is("Value Line - Research - Dashboard")
            )

            # navigate to the first stock page
            #TODO injecting value causes issue
            search_link = config.SEARCH_URL.format(ticker)
            driver.get(search_link)

            # wait maximum 20 seconds and search for the pdf module div
            #TODO catch timeout exception
            pdfs_div = WebDriverWait(driver, self.timeout).until(
                EC.visibility_of_element_located((By.XPATH, './/div[@data-module-name="HistoricalPdfs1View"]'))
            )

            # locate pdf download table and get all first columns' anchor elements
            anchors = pdfs_div.find_elements_by_xpath(".//table[contains(@class, 'report-results')]//td[1]//a")
    
            # loop through all anchor tags and download using href link
            for anchor in anchors:
                link = anchor.get_attribute("href")
                self.__download(driver, ticker, link, anchor.text)

        finally:
            driver.quit() #close the driver

    def __download(self, driver: webdriver, ticker: str, link: str, anchor_text: str):
        """
        """
        filename = ticker + "-" + anchor_text  # filename will be in the format <stock ticker>-<date>
        partial_file = "*.crdownload"

        # execute download
        driver.get(link)
    
        print("[{0}] is downloading {1}-{2}.pdf".format(current_process().name, ticker, anchor_text))
        dl_count = len(glob.glob1(self.base_download_path, partial_file))

        # max dl wait time ~5 seconds
        dl_wait = 5

        while dl_count > 0:
            if not dl_wait < 0:
                time.sleep(1)
                dl_wait -= 1 #decrement wait 
                dl_count = len(glob.glob1(self.base_download_path, partial_file))
                self.__rename_file(filename)
            else:
                #TODO pass wait seconds as parameter
                
                print("[{0}] error downloading {1}, file did not finishing downloading witin 5 seconds".format(current_process().name, filename))
                #TODO add error to the error queue
                

    def __rename_file(self, filename: str):
        """
        """
        default_name = "report.pdf" #default download name

        if glob.glob(self.base_download_path + default_name):
            os.rename(self.base_download_path + default_name, self.base_download_path  + filename)
        else:
            print("[{0}] error renaming file, file {1} does not exist".format(current_process().name, self.base_download_path + default_name))
            #TODO add error to error queue

def main():
    """
    """
    work_queue = multiprocessing.JoinableQueue()
    work_queue.put('AAPL')
    worker = Worker(config.BASE_DOWNLOAD_PATH, config.TIMEOUT, work_queue)
    worker.start()


if __name__ == "__main__":
    main()
