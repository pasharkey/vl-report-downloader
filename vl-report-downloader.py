import config
import glob
import time
import os
import multiprocessing
import shutil

from multiprocessing import current_process
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class Worker(multiprocessing.Process):
    def __init__(self, base_download_path: str, dest_path: str, timeout: int, queue: multiprocessing.JoinableQueue):
        """
        """
        multiprocessing.Process.__init__(self)
        self.base_download_path = base_download_path
        self.dest_path = dest_path
        self.timeout = timeout
        self.queue = queue
        self.stop_event = multiprocessing.Event()
        self.is_loggedin = False
        self.driver = None

    def stop(self):
        """
        """
        self.stop_event.set()

    def run(self):
        """
        """
        # create worker download directory
        self.__create_default_dir()

        # attempt to log in
        self.is_loggedin = self.__login()

        while not self.stop_event.is_set() and self.is_loggedin:

            if not self.queue.empty():
                ticker = self.queue.get()

                # execute search and download
                self.__search(self.driver, ticker)
            else:
                self.stop()

        # quit driver after everything is done
        if self.is_loggedin:
            self.driver.quit() #close the driver

    def __create_default_dir(self):
        """
        """
        worker_download_path = self.base_download_path + current_process().name + "/"
        # create directory if it does not exist
        if not os.path.exists(worker_download_path):
            os.makedirs(worker_download_path)

        # update base download path
        self.base_download_path = worker_download_path


    def __login(self):
        """
        """
        print("[{0}] logging in to the system".format(current_process().name))

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
            # wait maximum timeout for SSO login/redirect to occur
            WebDriverWait(driver, self.timeout).until(
                EC.title_is("Value Line - Research - Dashboard")
            )

            # set the driver for the worker
            self.driver = driver
            print("[{0}] successfully logged in".format(current_process().name))
            return True

        except TimeoutException:
            print("[{0}] error: login timed out ".format(current_process().name))
            return False

    def __reset(self, driver: webdriver, ticker: str):
        """
        """
        try:
            driver.get(config.RESET_URL)

            WebDriverWait(driver, self.timeout).until(
                EC.title_is("Value Line - Research - Browse Research")
            )

        except TimeoutException:
            print("[{0}] error: reset after search of {1} timed out after {2} seconds".format(current_process().name), ticker, self.timeout)

    def __search(self, driver: webdriver, ticker: str):
        """
        """
        print("[{0}] searching for {1}".format(current_process().name, ticker))
        
        # navigate to the first stock page
        search_link = config.SEARCH_URL.format(ticker)
        driver.get(search_link)

        # search for the pdf module div and wait maximum timeout
        try:
            pdfs_div = WebDriverWait(driver, self.timeout).until(
                EC.visibility_of_element_located((By.XPATH, './/div[@data-module-name="HistoricalPdfs1View"]'))
            )

        except TimeoutException:
            print("[{0}] error: could not locate pdf module for {1} within {2} seconds".format(current_process().name), ticker, self.timeout)

        # locate pdf download table and get all first columns' anchor elements
        anchors = pdfs_div.find_elements_by_xpath(".//table[contains(@class, 'report-results')]//td[1]//a")
    
        # loop through all anchor tags and download using href link
        for anchor in anchors:
            link = anchor.get_attribute("href")
            self.__download(driver, ticker, link, anchor.text)

        # move the files
        self.__move_files(ticker)

        # reset the search
        self.__reset(driver, ticker)


    def __download(self, driver: webdriver, ticker: str, link: str, anchor_text: str):
        """
        """
        filename = ticker + "-" + anchor_text  # filename will be in the format <stock ticker>-<date>
        partial_file = "*.crdownload"

        # execute download
        driver.get(link)
    
        print("[{0}] downloading {1}-{2}.pdf".format(current_process().name, ticker, anchor_text))
        dl_count = len(glob.glob1(self.base_download_path, partial_file))

        # max dl wait time ~5 seconds
        dl_wait = 0

        while dl_count > 0:
            if dl_wait < 5:
                time.sleep(1)
                dl_wait += 1 # increment wait counter
                dl_count = len(glob.glob1(self.base_download_path, partial_file))
                self.__rename_file(filename)
            else:                
                print("[{0}] error: {1} did not finish downloading witin 5 seconds".format(current_process().name, filename))
                break
                
    def __rename_file(self, filename: str):
        """
        """
        default_name = "report.pdf" # default download name

        if glob.glob(self.base_download_path + default_name):
            os.rename(self.base_download_path + default_name, self.base_download_path  + filename + ".pdf") 
        else:
            print("[{0}] error: attempted to rename file {1} that does not exist".format(current_process().name, self.base_download_path + default_name))

    def __move_files(self, ticker: str):
        """
        """
        # find all downloaded ticker files and move thme
        files = glob.glob('{0}{1}*.pdf'.format(self.base_download_path, ticker))

        if files:
            dest_ticker_path = '{0}{1}'.format(self.dest_path, ticker)

            # create directory if it does not exist
            if not os.path.exists(dest_ticker_path):
                os.makedirs(dest_ticker_path)

            # move the files
            for f in files:
                shutil.move(f, dest_ticker_path)
                #print("[{0}] moved {1} to {2}".format(current_process().name, f, dest_ticker_path))
def main():
    """
    """
    work_queue = multiprocessing.JoinableQueue()
    workers = []

    for w in range(0, 2):
        worker = Worker(config.BASE_DOWNLOAD_PATH, config.DEST_PATH, config.TIMEOUT, work_queue)
        workers.append(worker)
        worker.start()

    work_queue.put('AAPL')
    work_queue.put('MSFT')


if __name__ == "__main__":
    main()
