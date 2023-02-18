import os
import textwrap

import requests
import numpy as np
import matplotlib.pyplot as plt
from PIL import ImageFont, ImageDraw, Image
from dotenv import load_dotenv

load_dotenv()
HOME = os.path.dirname(__file__)


class Airly:
    lat, long = 50.0739491148, 20.0485859686
    url = f'https://airapi.airly.eu/v2/measurements/point?lat={lat}6&lng={long}'
    API_KEY = os.environ.get("AIRLY_KEY")
    EMOJIS = "😍😀🙂😐😟🤬💩"
    CAQI_BINS = np.array([20, 35, 50, 75, 100, 125])
    data = None

    def __init__(self) -> None:
        super().__init__()
        self.get_data()

    def get_data(self):
        headers = {'apikey': self.API_KEY, 'Accept': 'application/json'}
        response = requests.get(self.url, headers)
        self.data = response.json()

    def plot_caqi_history(self):
        caqis = [history['indexes'][0].get('value', 0) for history in self.data['history']]
        colors = [history['indexes'][0]['color'] for history in self.data['history']]
        times = [history['fromDateTime'].rsplit('T')[1][0:2] for history in self.data['history']]
        y_pos = np.arange(len(caqis))

        plt.figure(figsize=(7, 1))
        plt.bar(y_pos, caqis, color=colors, width=0.94)
        plt.xticks(y_pos, times)
        plt.savefig(os.path.join(HOME, 'caqi.png'), bbox_inches='tight')

    def fill_template(self):
        # load fonts
        open_moji = ImageFont.truetype(os.path.join(HOME, 'Manrope/OpenMoji-Black.ttf'), 60)
        manrope_extra_bold = ImageFont.truetype(os.path.join(HOME, 'Manrope/Manrope-ExtraBold.ttf'), 40)
        manrope_bold_small = ImageFont.truetype(os.path.join(HOME, 'Manrope/Manrope-Bold.ttf'), 30)
        manrope_regular_small = ImageFont.truetype(os.path.join(HOME, 'Manrope/Manrope-Regular.ttf'), 15)
        current_caqi = self.data['current']['indexes'][0]['value']
        emoji_index = np.digitize(current_caqi, self.CAQI_BINS)

        image = Image.open(os.path.join(HOME, 'master_template.png'))
        draw = ImageDraw.Draw(image)
        draw.text((9, 653), self.EMOJIS[emoji_index], fill="black", font=open_moji)
        advice = self.data['current']['indexes'][0]['advice']
        draw.text((9, 740), '\n'.join(textwrap.wrap(advice, width=45)), fill="black", font=manrope_regular_small)
        draw.text((70, 650), str(round(current_caqi)), fill="black", font=manrope_extra_bold)
        draw.text((195, 650), str(round(self.data['current']['values'][2]['value'])), fill="black", font=manrope_extra_bold)
        draw.text((350, 650), str(round(self.data['current']['values'][1]['value'])), fill="black", font=manrope_extra_bold)
        draw.text((505, 650), str(round(self.data['current']['values'][0]['value'])), fill="black", font=manrope_extra_bold)

        draw.text((195, 688), f"{round(100 * self.data['current']['values'][2]['value'] / 50.0)}%", fill="gray", font=manrope_bold_small)
        draw.text((350, 688), f"{round(100 * self.data['current']['values'][1]['value'] / 25.0)}%", fill="gray", font=manrope_bold_small)

        draw.text((350, 720), str(round(self.data['current']['values'][5]['value'])), fill="black", font=manrope_extra_bold)
        draw.text((505, 720), str(round(self.data['current']['values'][4]['value'])), fill="black", font=manrope_extra_bold)
        image.save(os.path.join(HOME, 'template.png'))
        image.close()
