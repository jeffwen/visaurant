from flask import Flask, jsonify,render_template, send_file, request
import pymongo
import pandas as pd
import json
from datetime import datetime
from flask_googlemaps import GoogleMaps
from flask.ext.googlemaps import Map
from collections import defaultdict
from nltk.corpus import stopwords
from bson.json_util import dumps

app = Flask(__name__)
GoogleMaps(app)

conn = pymongo.MongoClient()

db = conn['yelp']
restaurants = db.restaurants

photo_clusters = db.restaurant_photo_cluster

reviews = db.new_reviews

cachedStopWords = stopwords.words("english")


@app.route('/')
def hello_world():
    # return jsonify(results = test)
    #return 'Hello from Flask!'
    return "Cool hello world thing dude"

@app.route('/business/<businessid>')
def show_business_profile(businessid):
    data = restaurants.find_one({'business_id':businessid})

    # reformat and create hours table
    hours = pd.DataFrame(data['hours'])
    try:
        hours.columns = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    except ValueError:
        pass
    hours = hours.T
    hours['open'] = hours['open'].apply(lambda x: datetime.strftime(datetime.strptime(x, "%H:%M"),"%I:%M %p"))
    hours['close'] = hours['close'].apply(lambda x: datetime.strftime(datetime.strptime(x, "%H:%M"),"%I:%M %p"))
    hours.columns = ['Close', 'Open']
    hours = hours[['Open','Close']]

    # create dictionary with restaurant photo clusters
    clusters_cur = photo_clusters.find({'business_id':businessid})
    clusters = [i for i in clusters_cur]

    cluster_dict = defaultdict(list)
    for photo in clusters:
        cluster_dict[photo['cluster']] += [('https://s3-us-west-1.amazonaws.com/yelpphoto/yelp_restaurant_photo/' + photo['business_id'] + '/' + photo['photo_id'] + '.jpg',photo['caption'])]

    return render_template('restaurants.html', data=data, hours=hours, clusters=cluster_dict, businessid=businessid)

@app.route("/modal", methods=["POST"])
def modal():
    """
    When A POST request with json data is made to this uri,
    Read the example from the json, predict probability and
    send it with a response
    """
    # Get decision score for our example that came with the request
    print request.get_json()
    data = request.get_json()
    print data['text']
    caption, business_id = data['text'], data['business_id']
    new_words = [j.strip('.!?,/;:').lower() for j in caption.split() if j not in cachedStopWords and j.isalpha() and j!=None and j!='']
    new_caption = ' '.join(new_words)

    cur = reviews.find({"business_id":business_id,"$text":{"$search":new_caption}}, {'_id': False})
    review_list = [i for i in cur]

    # Put the result in a nice dict so we can send it as json
    return json.dumps(review_list)

if __name__ == '__main__':
  app.run(debug=True)

  
