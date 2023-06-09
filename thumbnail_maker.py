import logging
import multiprocessing
import os
import time
from multiprocessing import JoinableQueue, Value, Process
from queue import Queue, Empty
from threading import Thread, Lock
from urllib.parse import urlparse
from urllib.request import urlretrieve
from PIL import Image

FORMAT = '[%(threadName)s, %(asctime)s, %(levelname)s] %(message)s'
logging.basicConfig(filename='logfile.log', level=logging.DEBUG, format=FORMAT)


class ThumbnailMakerService:
    def __init__(self, home_dir='.'):
        self.home_dir = home_dir
        self.input_dir = self.home_dir + os.path.sep + 'incoming'
        self.output_dir = self.home_dir + os.path.sep + 'outgoing'
        self.img_queue = JoinableQueue()
        self.dl_size = 0
        self.resize_size = Value('i', 0, )

    def download_image(self, dl_queue, dl_size_lock):
        while not dl_queue.empty():
            try:
                url = dl_queue.get(block=False)
                img_filename = urlparse(url).path.split('/')[-1]
                logging.info(f'Download image {img_filename}')
                img_filename_ = self.input_dir + os.path.sep + str(img_filename)
                urlretrieve(url, img_filename_)
                with dl_size_lock:
                    self.dl_size += os.path.getsize(img_filename_)
                self.img_queue.put(img_filename)
                dl_queue.task_done()
            except Empty:
                logging.info('Queue is empty')

    def download_images(self, img_url_list):
        if not img_url_list:
            raise ValueError('Sth is no yes.')

        os.makedirs(self.input_dir, exist_ok=True)

        logging.info('Beginning image downloads.')

        start = time.perf_counter()

        for url in img_url_list:
            img_filename = urlparse(url).path.split('/')[-1]
            urlretrieve(url, self.input_dir + os.path.sep + str(img_filename))
            self.img_queue.put(img_filename)

        self.img_queue.put(None)

        stop = time.perf_counter()

        logging.info(f'Downloaded {len(img_url_list)} images in {stop - start} seconds')

    def perform_resizing(self):

        os.makedirs(self.output_dir, exist_ok=True)

        logging.info('Beginning resizing images')

        target_sizes = [32, 64, 200, 400, 500, 600, 700, 800, 1100, 1500, 2000]

        start = time.perf_counter()

        while True:
            filename = self.img_queue.get()
            if filename:
                logging.info(f'Resizing image {filename}.')
                original_image = Image.open(self.input_dir + os.path.sep + filename)
                for base_width in target_sizes:
                    width_percent = base_width / original_image.size[0]
                    height = int(original_image.size[1] * width_percent)
                    img = original_image.resize((base_width, height), Image.LANCZOS)
                    name, dot, extension = filename.partition('.')
                    new_filename = name + '_' + str(base_width) + dot + extension
                    img.save(self.output_dir + os.path.sep + new_filename)

                    with self.resize_size.get_lock():
                        self.resize_size.value = os.path.getsize(self.output_dir + os.path.sep + new_filename)

                os.remove(self.input_dir + os.path.sep + filename)
                logging.info(f'Done resizing image {filename}.')
                self.img_queue.task_done()
            else:
                self.img_queue.task_done()
                break

        stop = time.perf_counter()

        logging.info(f'Created {len(os.listdir(self.output_dir))} thumbnails in {stop - start} seconds.')

    def make_thumbnails(self, img_url_list):

        logging.info('START make_thumbnail.')

        start = time.perf_counter()

        dl_queue = Queue()
        dl_size_lock = Lock()

        for url in img_url_list:
            dl_queue.put(url)

        num_dl_threads = 26

        for _ in range(num_dl_threads):
            t = Thread(target=self.download_image, args=(dl_queue, dl_size_lock))
            t.start()

        num_processes = multiprocessing.cpu_count()

        for _ in range(num_processes):
            p = Process(target=self.perform_resizing)
            p.start()

        dl_queue.join()
        for _ in range(num_processes):
            self.img_queue.put(None)

        stop = time.perf_counter()

        logging.info(f"FINISHED. Ended make_thumbnails in {stop - start} seconds.")
        logging.info(f'Initial size of downloads {self.dl_size}. Final size of images {self.resize_size.value}')
