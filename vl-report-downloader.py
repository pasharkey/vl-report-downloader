import config
import glob
import time
import os
import multiprocessing
import shutil
import csv

from multiprocessing import current_process
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class Worker(multiprocessing.Process):
    def __init__(self, base_download_path: str, queue: multiprocessing.JoinableQueue):
        """
        """
        multiprocessing.Process.__init__(self)
        self.base_download_path = base_download_path
        self.worker_download_path = None
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
        self.worker_download_path = self.base_download_path + current_process().name + "/"
        self.__create_default_dir()

        # attempt to log in
        self.is_loggedin = self.__login()

        while not self.stop_event.is_set() and self.is_loggedin:

            if not self.queue.empty():
                ticker = self.queue.get()

                # execute search and download
                self.__search(self.driver, ticker)
            else:
                #TODO clean up worker download directory
                print("{0} [INFO] ticker queue is empty, stopping worker".format(current_process().name))
                self.stop()

        # quit driver after everything is done
        if self.is_loggedin:
            self.driver.quit() #close the driver

    def __create_default_dir(self):
        """
        """
        # create directory if it does not exist
        if not os.path.exists(self.worker_download_path):
            os.makedirs(self.worker_download_path)

    def __login(self):
        """
        """
        print("{0} [INFO] logging in to the system".format(current_process().name))

        #set up chrome optins to download files
        options = webdriver.ChromeOptions()
        options.add_experimental_option(
            "prefs", {
                "plugins.plugins_list": [
                    {"enabled":False,"name":"Chrome PDF Viewer"}
                ],
                "download.default_directory": self.worker_download_path,
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
            WebDriverWait(driver, config.LOGIN_TIMEOUT).until(
                EC.title_is("Value Line - Research - Dashboard")
            )

            # set the driver for the worker
            self.driver = driver
            print("{0} [INFO] successfully logged in".format(current_process().name))
            return True

        except TimeoutException:
            print("{0} [ERROR] login timed out ".format(current_process().name))
            return False

    def __reset(self, driver: webdriver, ticker: str):
        """
        """
        try:
            driver.get(config.RESET_URL)

            print("{0} [INFO] resetting search from [{1}]".format(current_process().name, ticker))

            WebDriverWait(driver, config.RESET_TIMEOUT).until(
                EC.title_is("Value Line - Research - Browse Research")
            )

        except TimeoutException:
            print("{0} [ERROR] reset after search of [{1}] timed out after {2} "
                "seconds".format(current_process().name, ticker, config.RESET_TIMEOUT))
            pass

    def __search(self, driver: webdriver, ticker: str):
        """
        """
        print("{0} [INFO] searching for [{1}]".format(current_process().name, ticker))
        
        # navigate to the first stock page
        search_link = config.SEARCH_URL.format(ticker)
        driver.get(search_link)

        # search for the pdf module div and wait maximum timeout
        try:
            pdfs_div = WebDriverWait(driver, config.SEARCH_TIMEOUT).until(
                EC.visibility_of_element_located((By.XPATH, './/div[@data-module-name="HistoricalPdfs1View"]'))
            )

             # locate pdf download table and get all first columns' anchor elements
            anchors = pdfs_div.find_elements_by_xpath(".//table[contains(@class, 'report-results')]//td[1]//a")
    
            # loop through all anchor tags and download using href link
            try :
                for anchor in anchors:
                    link = anchor.get_attribute("href")
                    self.__download(driver, ticker, link, anchor.text)

                # move the files
                self.__move_files(ticker)

            except StaleElementReferenceException: 
                print("{0} [ERROR] stale element exception for {1}".formt(current_process().name, ticker))
                pass

                #TODO clear the files?

        except TimeoutException:
            print("{0} [WARN] could not locate pdf module for {1} within {2} "
                "seconds".format(current_process().name, ticker, config.SEARCH_TIMEOUT))
            pass

        # reset the search
        self.__reset(driver, ticker)

    def __download(self, driver: webdriver, ticker: str, link: str, anchor_text: str):
        """
        """
        filename = ticker + "-" + anchor_text  # filename will be in the format <stock ticker>-<date>
        report_file = "report*.pdf"

        # execute download
        driver.get(link)
    
        print("{0} [INFO] downloading {1}-{2}.pdf".format(current_process().name, ticker, anchor_text))

        report_present = len(glob.glob1(self.worker_download_path, report_file))

        while not report_present: 
                time.sleep(1)
                report_present = len(glob.glob1(self.worker_download_path, report_file))

        if report_present > 1:
            print("{0} [ERROR] found {1} reports in download folder for {2}".format(current_process().name, report_present, ticker))
            #TODO handle this edge case
        else: 
            #rename the donwloaded file
            self.__rename_file(filename)
                
    def __rename_file(self, filename: str):
        """
        """
        # TODO figure out report(1).pdf bug
        temp_file = glob.glob(self.worker_download_path + "report*.pdf")

        if len(temp_file) == 1:

            final_path = self.worker_download_path  + filename + ".pdf"
            print("{0} [INFO] renaming {1} to {2}".format(current_process().name, temp_file[0], final_path))
            os.rename(temp_file[0], final_path) 

            # wait until file exists
            # TODO timeout after certain time
            while os.path.exists(temp_file[0]):
                print("{0} [INFO] waiting for {1} to be renamed to {2}".format(current_process().name, temp_file[0], final_path))
                time.sleep(1)

        elif len(temp_file) > 1:
            print("{0} [ERROR] multiple files with pattern report*.pdf at {1}"
                "exist, {2}".format(current_process().name, self.worker_download_path, str(temp_file)))

            #TODO remove all files to fix issue

        else:
            print("{0} [ERRPR] attempted to rename file report*.pdf that does not "
                "exist {1}".format(current_process().name, temp_file))

    def __move_files(self, ticker: str):
        """
        """
        # find all downloaded ticker files and move thme
        files = glob.glob('{0}{1}*.pdf'.format(self.worker_download_path, ticker))

        if files:
            dest_ticker_path = '{0}{1}'.format(self.base_download_path, ticker)

            # create directory if it does not exist
            if not os.path.exists(dest_ticker_path):
                os.makedirs(dest_ticker_path)

            # move the files
            for f in files:
                shutil.move(f, dest_ticker_path)
                print("{0} [INFO] moved {1} to {2}".format(current_process().name, f, dest_ticker_path))

def create_ticker_list(ticker_csv: str):
    """
    """
    ticker_list = []

    with open(ticker_csv, 'r') as f:
        reader = csv.reader(f, delimiter=',')

        #skip first line in csv
        next(reader) 
        for row in reader:
            ticker_list.append(row[0])

    return ticker_list

def main():
    """
    """
    nasdaq_tickers = create_ticker_list(config.NASDAQ_CSV)
    nyse_tickers = create_ticker_list(config.NYSE_CSV)

    work_queue = multiprocessing.JoinableQueue()
    workers = []

    # add tickers to the queue
    for ticker in nyse_tickers:
        work_queue.put(ticker)

    #work_queue.put('ACIA')
    #work_queue.put('ABIL')
    #work_queue.put('AAPL')
    #work_queue.put('XO')
    #work_queue.put('PHIL')

    for w in range(0, 5):
        worker = Worker(config.BASE_DOWNLOAD_PATH, work_queue)
        workers.append(worker)
        worker.start()

        #sleep to allow worker to log in
        time.sleep(2)



if __name__ == "__main__":
    main()
