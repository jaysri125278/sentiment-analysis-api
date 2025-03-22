from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from pymongo import MongoClient
import bcrypt
from flask_cors import CORS
from datetime import datetime,timedelta
import time
from transformers import pipeline

app = Flask(__name__)

CORS(app)

# Secret key for JWT
app.config['JWT_SECRET_KEY'] = '9b1f4b0b2c4df0d3be57e0b3f62e79b33b4c7a2b6e46e0b3b0136e9fe6b4e597'
jwt = JWTManager(app)

# MongoDB connection
client = MongoClient('mongodb+srv://saravananjaysri:0vj2JgUyBB9utubl@cluster0.lf4cc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
db = client['sentimentDashboard']
users_collection = db['Users']
reviews_collection = db['Reviews']  # Create a Reviews collection

sentiment_model = pipeline(
    "sentiment-analysis", 
    model="finiteautomata/bertweet-base-sentiment-analysis",
)
# Register Route
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    email = data['email']
    password = data['password']

    user = users_collection.find_one({'username': username})
    if user:
        return jsonify({'message': 'Username already exists'}), 400
    
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    users_collection.insert_one({'username': username, 'email': email, 'password': hashed_password})

    return jsonify({'message': 'User inserted successfully'}), 200

# Login Route
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data['username']
    password = data['password']

    user = users_collection.find_one({'username': username})
    if not user:
        return jsonify({'message': 'Invalid username and password'}), 401
    
    if not bcrypt.checkpw(password.encode('utf-8'), user['password']):
        return jsonify({'message': 'Invalid username and password'}), 401
    
    access_token = create_access_token(identity=username)
    return jsonify({'access_token': access_token}), 200

@app.route('/submit_review', methods=['POST'])
@jwt_required()  # Only authenticated users can submit a review
def submit_review():
    current_user = get_jwt_identity()  # Get the current user's username from the JWT token
    
    # Get the review data from the request
    data = request.get_json()
    review_text = data.get('review_text')
    
    if not review_text:
        return jsonify({'message': 'Review text is required'}), 400

    # Perform sentiment analysis using Hugging Face model
    sentiment_result = sentiment_model(review_text)[0]  # Get sentiment prediction
    sentiment = sentiment_result['label']  # Sentiment label (e.g., "POSITIVE" or "NEGATIVE")
    confidence = sentiment_result['score']  # Confidence score

    # Prepare review document to be inserted into the Reviews collection
    review = {
        'user_id': current_user,
        'review_text': review_text,
        'sentiment': sentiment,
        'confidence': confidence,
        'created_at': datetime.utcnow() - timedelta(days=1)
    }

    # Insert the review into the database
    reviews_collection.insert_one(review)

    # Return sentiment label and confidence to the user
    return jsonify({
        'message': 'Review submitted successfully',
        'sentiment': sentiment,
        'confidence': confidence
    }), 200

# Route to get all reviews (for displaying)
@app.route('/reviews', methods=['GET'])
@jwt_required()  # Only authenticated users can view reviews
def get_reviews():
    # Get all reviews from the 'Reviews' collection
    reviews = reviews_collection.find()
    reviews_list = []
    for review in reviews:
        reviews_list.append({
            'user_id': review['user_id'],
            'review_text': review['review_text'],
            'created_at': review['created_at']
        })
    
    return jsonify({'reviews': reviews_list}), 200


# Endpoint to fetch sentiment distribution over time
@app.route('/dashboard/sentiment_distribution', methods=['GET'])
def sentiment_distribution():
    # Group reviews by date and sentiment
    pipeline = [
        {
            '$group': {
                '_id': {
                    'date': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$created_at'}},
                    'sentiment': '$sentiment'
                },
                'count': {'$sum': 1}
            }
        },
        {
            '$sort': {'_id.date': 1}
        }
    ]
    
    result = list(reviews_collection.aggregate(pipeline))
    
    # Format result for easier use in the frontend
    sentiment_data = {}
    for entry in result:
        date = entry['_id']['date']
        sentiment = entry['_id']['sentiment']
        count = entry['count']
        
        if date not in sentiment_data:
            sentiment_data[date] = {'POSITIVE': 0, 'NEGATIVE': 0}
        
        sentiment_data[date][sentiment] = count
    
    return jsonify(sentiment_data), 200

# Endpoint to fetch recent reviews
@app.route('/dashboard/recent_reviews', methods=['GET'])
def recent_reviews():
    reviews = list(reviews_collection.find().sort('created_at', -1).limit(5))
    
    # Format recent reviews data
    recent_reviews = [{
        'user_id': review['user_id'],
        'review_text': review['review_text'],
        'sentiment': review['sentiment'],
        'confidence': review['confidence'],
        'created_at': review['created_at']
    } for review in reviews]
    
    return jsonify(recent_reviews), 200

# Endpoint to filter reviews by date range
@app.route('/dashboard/reviews_by_date', methods=['POST'])
def reviews_by_date():
    data = request.get_json()
    start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
    end_date = datetime.strptime(data['end_date'], '%Y-%m-%d')
    
    reviews = list(reviews_collection.find({
        'created_at': {'$gte': start_date, '$lte': end_date}
    }))
    
    filtered_reviews = [{
        'user_id': review['user_id'],
        'review_text': review['review_text'],
        'sentiment': review['sentiment'],
        'confidence': review['confidence'],
        'created_at': review['created_at']
    } for review in reviews]
    
    return jsonify(filtered_reviews), 200


if __name__ == '__main__':
    app.run(debug=True)
