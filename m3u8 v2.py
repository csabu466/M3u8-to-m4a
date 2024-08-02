import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog, QLineEdit, QTextEdit, QLabel, QProgressBar, QGridLayout, QTabWidget, QMessageBox, QHBoxLayout
from PyQt5.QtCore import Qt
import pyperclip
import requests
import m3u8
import ffmpeg
import os
import shutil
from mutagen.mp4 import MP4, MP4Cover
import concurrent.futures

class M3U8Downloader(QWidget):
    def __init__(self):
        super().__init__()
        self.link_number = 1
        self.initUI()

    def initUI(self):
        self.setGeometry(100, 100, 800, 600)
        self.setWindowTitle('M3U8 Downloader')
        self.setStyleSheet("background-color: #dffaff;")

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.create_clipboard_tab(), "Clipboard Link Organizer")
        self.tab_widget.addTab(self.create_download_tab(), "M3U8 Downloader")
        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

    def create_download_tab(self):
        download_tab = QWidget()
        grid_layout = QGridLayout()

        self.import_from_clipboard_button = QPushButton('Import from Clipboard')
        self.import_from_clipboard_button.clicked.connect(self.import_from_clipboard)
        grid_layout.addWidget(self.import_from_clipboard_button, 0, 0, 1, 2)

        self.link_preview = QTextEdit()
        grid_layout.addWidget(self.link_preview, 1, 0, 1, 2)

        self.output_location_label = QLabel("Output Location:")
        grid_layout.addWidget(self.output_location_label, 2, 0)
        self.output_location_entry = QLineEdit()
        grid_layout.addWidget(self.output_location_entry, 2, 1)
        self.output_location_button = QPushButton('Browse')
        self.output_location_button.clicked.connect(self.browse_output_location)
        grid_layout.addWidget(self.output_location_button, 2, 2)

        self.filename_prefix_label = QLabel("Filename Prefix:")
        grid_layout.addWidget(self.filename_prefix_label, 3, 0)
        self.filename_prefix_entry = QLineEdit()
        grid_layout.addWidget(self.filename_prefix_entry, 3, 1)

        self.album_art_label = QLabel("Album Art:")
        grid_layout.addWidget(self.album_art_label, 4, 0)
        self.album_art_entry = QLineEdit()
        grid_layout.addWidget(self.album_art_entry, 4, 1)
        self.album_art_button = QPushButton('Browse')
        self.album_art_button.clicked.connect(self.browse_album_art)
        grid_layout.addWidget(self.album_art_button, 4, 2)

        self.download_button = QPushButton('Download')
        self.download_button.clicked.connect(self.download_m3u8)
        grid_layout.addWidget(self.download_button, 5, 0, 1, 2)

        self.progress_bar = QProgressBar()
        grid_layout.addWidget(self.progress_bar, 6, 0, 1, 2)

        download_tab.setLayout(grid_layout)
        return download_tab

    def import_from_clipboard(self):
        links = pyperclip.paste()
        self.link_preview.setText(links)

    def browse_output_location(self):
        output_location = QFileDialog.getExistingDirectory()
        self.output_location_entry.setText(output_location)

    def browse_album_art(self):
        album_art_location, _ = QFileDialog.getOpenFileName()
        self.album_art_entry.setText(album_art_location)

    def download_segment(self, segment_url, temp_folder, segment_number):
        try:
            response = requests.get(segment_url, stream=True)
            if response.status_code == 200:
                temp_file = os.path.join(temp_folder, f"f_{segment_number}.ts")
                with open(temp_file, 'wb') as file:
                    for chunk in response.iter_content(1024):
                        file.write(chunk)
            else:
                print(f"Failed to download segment {segment_number}: {segment_url}")
        except Exception as e:
            print(f"Error downloading segment {segment_number}: {e}")

    def download_m3u8(self):
        links = self.link_preview.toPlainText()
        output_location = self.output_location_entry.text()
        filename_prefix = self.filename_prefix_entry.text()
        album_art_location = self.album_art_entry.text()

        if not links or not output_location or not filename_prefix:
            print("Please fill in all required fields.")
            return

        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(links.splitlines()))

        link_number = 1
        for link in links.splitlines():
            try:
                temp_folder = os.path.join(output_location, f".temp_{link_number}")
                os.makedirs(temp_folder, exist_ok=True)

                m3u8_obj = m3u8.load(link)
                base_url = link.rsplit('/', 1)[0] + '/'
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = []
                    for i, segment in enumerate(m3u8_obj.segments):
                        segment_url = base_url + segment.uri
                        futures.append(executor.submit(self.download_segment, segment_url, temp_folder, i))
                    for future in concurrent.futures.as_completed(futures):
                        future.result()

                # Combine all TS files into a single file
                combined_ts_file = os.path.join(temp_folder, "combined.ts")
                with open(combined_ts_file, 'wb') as outfile:
                    for i in range(len(m3u8_obj.segments)):
                        temp_file = os.path.join(temp_folder, f"f_{i}.ts")
                        with open(temp_file, 'rb') as infile:
                            outfile.write(infile.read())

                # Convert combined TS file to M4A
                output_file = os.path.join(output_location, f"{filename_prefix}_{link_number}.m4a")
                if os.path.exists(output_file):
                    base, ext = os.path.splitext(output_file)
                    i = 1
                    while os.path.exists(f"{base}_{i}{ext}"):
                        i += 1
                    output_file = f"{base}_{i}{ext}"
                try:
                    ffmpeg.input(combined_ts_file).output(output_file, c='copy').run(capture_stdout=True, capture_stderr=True)
                    audio = MP4(output_file)
                    with open(album_art_location, 'rb') as f:
                        audio['covr'] = [MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG)]
                    audio.save()
                    shutil.rmtree(temp_folder)
                    print(f"Downloaded file {link_number}: {output_file}")
                except ffmpeg.Error as e:
                    print(f"Error converting combined TS file for link {link_number}: {e.stderr.decode('utf-8')}")
                link_number += 1
                self.progress_bar.setValue(link_number)
            except Exception as e:
                print(f"Error downloading link {link_number}: {e}")

        for temp_folder in [f for f in os.listdir(output_location) if f.startswith('.temp_')]:
            shutil.rmtree(os.path.join(output_location, temp_folder))
        print("All temporary folders removed.")
    
    def create_clipboard_tab(self):
        clipboard_tab = QWidget()
        self.clipboard_app = ClipboardLinkOrganizer()
        layout = QVBoxLayout()
        layout.addWidget(self.clipboard_app)
        clipboard_tab.setLayout(layout)
        return clipboard_tab

class ClipboardLinkOrganizer(QWidget):
    def __init__(self):
        super().__init__()
        self.links = []
        self.initUI()

    def initUI(self):
        self.setGeometry(100, 100, 600, 400)
        self.setWindowTitle('Clipboard Link Organizer')

        self.main_layout = QVBoxLayout()

        self.search_layout = QHBoxLayout()
        self.search_entry = QLineEdit()
        self.search_button = QPushButton('Search')
        self.search_button.clicked.connect(self.search_links)
        self.search_layout.addWidget(self.search_entry)
        self.search_layout.addWidget(self.search_button)

        self.links_text = QTextEdit()
        self.links_text.setReadOnly(True)

        self.button_layout = QHBoxLayout()
        self.import_button = QPushButton('Import from Clipboard')
        self.import_button.clicked.connect(self.import_from_clipboard)
        self.export_button = QPushButton('Export to Clipboard')
        self.export_button.clicked.connect(self.export_to_clipboard)
        self.clear_button = QPushButton('Clear')
        self.clear_button.clicked.connect(self.clear_links)
        self.button_layout.addWidget(self.import_button)
        self.button_layout.addWidget(self.export_button)
        self.button_layout.addWidget(self.clear_button)

        self.main_layout.addLayout(self.search_layout)
        self.main_layout.addWidget(self.links_text)
        self.main_layout.addLayout(self.button_layout)

        self.setLayout(self.main_layout)

    def search_links(self):
        query = self.search_entry.text()
        filtered_links = [link for link in reversed(self.links) if query in link]
        self.links_text.clear()
        for link in filtered_links:
            self.links_text.append(link)

    def import_from_clipboard(self):
        links = pyperclip.paste().split("\n")
        self.links.extend(links)
        self.display_links()

    def display_links(self):
        self.links_text.clear()
        for link in reversed(self.links):
            self.links_text.append(link)

    def export_to_clipboard(self):
        query = self.search_entry.text()
        filtered_links = [link for link in reversed(self.links) if query in link]
        pyperclip.copy("\n".join(filtered_links))
        QMessageBox.information(self, "Exported", "Filtered links exported to clipboard")

    def clear_links(self):
        self.links = []
        self.links_text.clear()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = M3U8Downloader()
    ex.show()
    sys.exit(app.exec_())
