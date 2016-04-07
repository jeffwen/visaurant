from flask import Flask, jsonify,render_template, send_file, request, redirect, url_for
import pymongo
import pandas as pd
import json
from datetime import datetime
from flask_googlemaps import GoogleMaps
from flask.ext.googlemaps import Map
from collections import defaultdict
from nltk.corpus import stopwords
import random
from bson.json_util import dumps
import recsys.algorithm
from recsys.algorithm.factorize import SVD


app = Flask(__name__)

# loading Google maps generator for the restaurant pages
GoogleMaps(app)

# Connecting to mongoDB
conn = pymongo.MongoClient()

db = conn['yelp']

# Storing restaurant (business) details
restaurants = db.restaurants

# Storing photo information
photo_clusters = db.restaurant_photo_cluster

# Extracting review details
reviews = db.new_reviews

# Stop words to be removed from the captions when searching for reviews
cachedStopWords = stopwords.words("english")

# creating a Df of the restaurant and User IDs
df = pd.read_csv('static/data/review_df_clean.csv')

# recommending similar restaurants based on their selection
svd = SVD()
svd.load_data(filename='static/data/review_df_clean.csv', sep=",", format = {'col':1, 'row':2, 'value':3, 'ids': str})
k = 100
svd.compute(k=k, min_values=5, pre_normalize=None, mean_center=True, post_normalize=True)

@app.route('/business/<businessid>/')
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
    clusters = [i for i in clusters_cur if 'cluster' in i]

    cluster_dict = defaultdict(list)
    for photo in clusters:
        if photo['caption'] != None and photo['caption'] != '':
            new_caption = photo['caption']
        else:
            new_caption = 'None'
        cluster_dict[photo['cluster']] += [('https://s3-us-west-1.amazonaws.com/yelpphoto/yelp_restaurant_photo/' + photo['business_id'] + '/' + photo['photo_id'] + '.jpg',new_caption)]

    return render_template('restaurants_grid.html', data=data, hours=hours, clusters=cluster_dict, businessid=businessid)

@app.route("/reviews", methods=["POST"])
def get_reviews():
    """    When A POST request with json data is made to this uri,
    Read the example from the json and return the reviews associated with the image
    """
    # extract the data from the post and run it through mongo to search for the relevant items
    data = request.get_json()
    caption, business_id = data['text'], data['business_id']
    new_words = [j.strip('.!?,/;:').lower() for j in caption.split() if j not in cachedStopWords and j.isalpha() and j!=None and j!='']
    new_caption = ' '.join(new_words)

    cur = reviews.find({"business_id":business_id,"$text":{"$search":new_caption}}, {'_id': False})
    review_list = [i for i in cur]

    return json.dumps(review_list)

@app.route("/")
def show_recommendation_page():
    restaurant_set = set(df.business_id)
    recommended_restaurants = random.sample(restaurant_set,12)
    # recommended_restaurants = ['xNcqwYAUeVOhe3KNC4Xjaw','iUPJmJvHy9fVfRxsuwwdLQ']

    # testing
    recommended_restaurants[0]='xNcqwYAUeVOhe3KNC4Xjaw'
    recommended_restaurants[9]='iUPJmJvHy9fVfRxsuwwdLQ'
    # testing
    
    restaurant_dict = defaultdict(list)
    detail_dict = defaultdict(list)
    
    for restaurant in recommended_restaurants:
        print restaurant
        link = 'https://s3-us-west-1.amazonaws.com/yelpphoto/yelp_restaurant_photo/' + restaurant + '/'
        photo_cur = photo_clusters.find({'business_id':restaurant}).limit(4)
        photos = [link+i['photo_id']+'.jpg' for i in photo_cur]
        restaurant_dict[restaurant] = photos
        detail_cur = restaurants.find_one({"business_id":restaurant})
        detail_dict[restaurant] = [detail_cur['name'],detail_cur['stars']]
        
    return render_template('recommend.html', restaurant_dict=restaurant_dict, detail_dict=detail_dict)

@app.route("/get_recs", methods=["POST"])
def get_recs():
    data = request.get_json()
    selections = data['selections']
    data_dict = defaultdict(list)
    for selection in selections[:-1]:
        similar_restaurants,_ = zip(*svd.similar(selection, n=2))
        rec = similar_restaurants[1]
        restaurant_info = restaurants.find_one({"business_id":rec})
        link = 'https://s3-us-west-1.amazonaws.com/yelpphoto/yelp_restaurant_photo/' + rec + '/'
        photo_cur = photo_clusters.find({'business_id':rec}).limit(5)
        photos = [link+i['photo_id']+'.jpg' for i in photo_cur]
        data_dict[(rec,restaurant_info['name'])] = photos

    # testing
    rec = 'AYbUb5UcAngroJ6uJG7tLQ'
    restaurant_info = restaurants.find_one({"business_id":rec})
    link = 'https://s3-us-west-1.amazonaws.com/yelpphoto/yelp_restaurant_photo/' + rec + '/'
    photo_cur = photo_clusters.find({'business_id':rec}).limit(5)
    photos = [link+i['photo_id']+'.jpg' for i in photo_cur]
    data_dict[(rec,restaurant_info['name'])] = photos
    # testing
    
    # write html with python...
    final_div = ''
    for key, values in data_dict.items():
        div = "<div class='recommended_rest' data-group='recommendations' id='"+key[0]+"'><span class='text-content' data-group='recommendations' id='"+key[0]+"'><span data-group='recommendations' id='"+key[0]+"'>"+key[1]+"</span></span>"
        for url in values:
            div += "<div class='recommended_rest_photo' data-group='recommendations' id='"+key[0]+ "' style='background-image:url("+url+ ")'></div>"
        div += "</div>"
        final_div += div
    aDict = {}
    aDict['html'] = final_div
    return json.dumps(aDict)

@app.route("/redirect_me", methods=["POST"])
def redirect_me():
    data = request.get_json()
    businessid = data['url']
    return json.dumps(url_for('show_business_profile', businessid=str(businessid)))

if __name__ == '__main__':
    app.run(debug=True)

  
