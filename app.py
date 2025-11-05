from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///farmers_market.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Models - Define all models first without relationships that reference undefined classes
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)  # 'farmer' or 'customer'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(50))
    image_url = db.Column(db.String(200))
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, shipped, delivered, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    order_items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Add farmer_id to track who needs to fulfill

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

# Now add relationships after all classes are defined
# User relationships
User.products = db.relationship('Product', backref='farmer', lazy=True, foreign_keys='Product.farmer_id')
User.orders = db.relationship('Order', backref='customer', lazy=True, foreign_keys='Order.customer_id')
User.written_reviews = db.relationship('Review', backref='author', lazy=True, foreign_keys='Review.customer_id')
User.received_reviews = db.relationship('Review', backref='farmer_received', lazy=True, foreign_keys='Review.farmer_id')
User.cart_items = db.relationship('Cart', backref='cart_owner', lazy=True, foreign_keys='Cart.customer_id')

# Product relationships
Product.order_items = db.relationship('OrderItem', backref='product', lazy=True)
Product.reviews = db.relationship('Review', backref='product', lazy=True, foreign_keys='Review.product_id')  # Fixed this line
Product.in_carts = db.relationship('Cart', backref='cart_product', lazy=True, foreign_keys='Cart.product_id')

# Order relationships
Order.order_items = db.relationship('OrderItem', backref='order', lazy=True)

# Cart relationships
Cart.product = db.relationship('Product', backref='product_carts', lazy=True, foreign_keys='Cart.product_id')

# Review relationships - Add these missing relationships
Review.product_rel = db.relationship('Product', backref='reviewed_products', lazy=True, foreign_keys='Review.product_id')
Review.customer_rel = db.relationship('User', backref='reviewing_customers', lazy=True, foreign_keys='Review.customer_id')
Review.farmer_rel = db.relationship('User', backref='reviewed_farmers', lazy=True, foreign_keys='Review.farmer_id')
oduct = db.relationship('Product', backref='product_carts', lazy=True, foreign_keys='Cart.product_id')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    products = Product.query.filter(Product.quantity > 0).limit(8).all()
    return render_template('index.html', products=products)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/marketplace')
def marketplace():
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    
    query = Product.query.filter(Product.quantity > 0)
    
    if category:
        query = query.filter(Product.category == category)
    if search:
        query = query.filter(Product.name.contains(search))
    
    products = query.all()
    
    # Calculate average ratings for each product
    for product in products:
        product_reviews = Review.query.filter_by(product_id=product.id).all()
        if product_reviews:
            product.avg_rating = sum(review.rating for review in product_reviews) / len(product_reviews)
            product.avg_rating = round(product.avg_rating, 1)
            product.review_count = len(product_reviews)
        else:
            product.avg_rating = 0
            product.review_count = 0
    
    categories = db.session.query(Product.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    return render_template('marketplace.html', products=products, categories=categories)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            user_type=user_type
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Login successful!')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.user_type == 'farmer':
        products = Product.query.filter_by(farmer_id=current_user.id).all()
        total_products = len(products)
        received_reviews_count = Review.query.filter_by(farmer_id=current_user.id).count()
        
        return render_template('dashboard.html', 
                             products=products, 
                             total_products=total_products,
                             received_reviews_count=received_reviews_count)
    else:
        orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).all()
        total_orders = len(orders)
        cart_items_count = Cart.query.filter_by(customer_id=current_user.id).count()
        
        return render_template('dashboard.html', 
                             orders=orders, 
                             total_orders=total_orders,
                             cart_items_count=cart_items_count)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.email = request.form['email']
        db.session.commit()
        flash('Profile updated successfully!')
        return redirect(url_for('profile'))
    
    return render_template('profile.html')

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if current_user.user_type != 'farmer':
        flash('Only farmers can add products')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        product = Product(
            name=request.form['name'],
            description=request.form['description'],
            price=float(request.form['price']),
            quantity=int(request.form['quantity']),
            category=request.form['category'],
            farmer_id=current_user.id
        )
        
        db.session.add(product)
        db.session.commit()
        flash('Product added successfully!')
        return redirect(url_for('my_products'))
    
    return render_template('add_product.html')

@app.route('/my_products')
@login_required
def my_products():
    if current_user.user_type != 'farmer':
        flash('Only farmers can view their products')
        return redirect(url_for('dashboard'))
    
    products = Product.query.filter_by(farmer_id=current_user.id).all()
    return render_template('my_products.html', products=products)

@app.route('/cart')
@login_required
def cart():
    if current_user.user_type != 'customer':
        flash('Only customers can view cart')
        return redirect(url_for('dashboard'))
    
    cart_items = Cart.query.filter_by(customer_id=current_user.id).all()
    total = 0
    for item in cart_items:
        if item.product:
            total += item.quantity * item.product.price
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    if current_user.user_type != 'customer':
        return jsonify({'success': False, 'message': 'Only customers can add to cart'})
    
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 1))
    
    if quantity > product.quantity:
        return jsonify({'success': False, 'message': 'Not enough stock'})
    
    cart_item = Cart.query.filter_by(customer_id=current_user.id, product_id=product_id).first()
    
    if cart_item:
        new_quantity = cart_item.quantity + quantity
        if new_quantity > product.quantity:
            return jsonify({'success': False, 'message': 'Not enough stock'})
        cart_item.quantity = new_quantity
    else:
        cart_item = Cart(customer_id=current_user.id, product_id=product_id, quantity=quantity)
        db.session.add(cart_item)
    
    db.session.commit()
    return jsonify({'success': True, 'message': 'Product added to cart'})

@app.route('/remove_from_cart/<int:cart_item_id>', methods=['POST'])
@login_required
def remove_from_cart(cart_item_id):
    if current_user.user_type != 'customer':
        flash('Only customers can remove from cart')
        return redirect(url_for('dashboard'))
    
    cart_item = Cart.query.filter_by(id=cart_item_id, customer_id=current_user.id).first()
    if cart_item:
        db.session.delete(cart_item)
        db.session.commit()
        flash('Item removed from cart')
    
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    if current_user.user_type != 'customer':
        flash('Only customers can checkout')
        return redirect(url_for('dashboard'))
    
    cart_items = Cart.query.filter_by(customer_id=current_user.id).all()
    
    if not cart_items:
        flash('Your cart is empty')
        return redirect(url_for('cart'))
    
    # Create order
    total_amount = sum(item.quantity * item.product.price for item in cart_items)
    order = Order(customer_id=current_user.id, total_amount=total_amount, status='pending')
    db.session.add(order)
    db.session.commit()
    
    # Create order items and update product quantities
    for cart_item in cart_items:
        product = Product.query.get(cart_item.product_id)
        if product.quantity < cart_item.quantity:
            db.session.rollback()
            flash(f'Not enough stock for {product.name}')
            return redirect(url_for('cart'))
        
        product.quantity -= cart_item.quantity
        order_item = OrderItem(
            order_id=order.id,
            product_id=cart_item.product_id,
            quantity=cart_item.quantity,
            price=product.price,
            farmer_id=product.farmer_id  # Track which farmer needs to fulfill this item
        )
        db.session.add(order_item)
    
    # Clear cart
    Cart.query.filter_by(customer_id=current_user.id).delete()
    db.session.commit()
    
    flash('Order placed successfully!')
    return redirect(url_for('orders'))

@app.route('/orders')
@login_required
def orders():
    if current_user.user_type != 'customer':
        flash('Only customers can view orders')
        return redirect(url_for('dashboard'))
    
    # Get orders for the current customer
    orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).all()
    
    return render_template('orders.html', orders=orders)

@app.route('/add_review/<int:product_id>', methods=['GET', 'POST'])
@login_required
def add_review(product_id):
    if current_user.user_type != 'customer':
        flash('Only customers can add reviews')
        return redirect(url_for('marketplace'))
    
    product = Product.query.get_or_404(product_id)
    
    # For demo purposes, we'll skip the purchase verification
    has_purchased = True  # Set to True for testing
    
    if not has_purchased:
        flash('You can only review products you have purchased')
        return redirect(url_for('product_details', product_id=product_id))
    
    # Check if user already reviewed this product
    existing_review = Review.query.filter_by(
        product_id=product_id, 
        customer_id=current_user.id
    ).first()
    
    if existing_review:
        flash('You have already reviewed this product')
        return redirect(url_for('product_details', product_id=product_id))
    
    if request.method == 'POST':
        rating = int(request.form['rating'])
        comment = request.form['comment']
        
        review = Review(
            product_id=product_id,
            customer_id=current_user.id,
            farmer_id=product.farmer_id,
            rating=rating,
            comment=comment
        )
        
        db.session.add(review)
        db.session.commit()
        
        flash('Review added successfully!')
        return redirect(url_for('product_details', product_id=product_id))
    
    return render_template('add_review.html', product=product)

@app.route('/product/<int:product_id>')
def product_details(product_id):
    product = Product.query.get_or_404(product_id)
    reviews = Review.query.filter_by(product_id=product_id).all()
    
    # Calculate average rating
    if reviews:
        avg_rating = sum(review.rating for review in reviews) / len(reviews)
        avg_rating = round(avg_rating, 1)
    else:
        avg_rating = 0
    
    # For demo purposes, allow all customers to review
    can_review = False
    if current_user.is_authenticated and current_user.user_type == 'customer':
        has_reviewed = Review.query.filter_by(
            product_id=product_id,
            customer_id=current_user.id
        ).first()
        
        can_review = not has_reviewed
    
    return render_template('product_details.html', 
                         product=product, 
                         reviews=reviews, 
                         avg_rating=avg_rating,
                         can_review=can_review)


@app.route('/farmer_reviews')
@login_required
def farmer_reviews():
    if current_user.user_type != 'farmer':
        flash('Only farmers can view this page')
        return redirect(url_for('dashboard'))
    
    # Use join to get all data in one query
    reviews_data = db.session.query(Review, Product, User).\
        select_from(Review).\
        join(Product, Review.product_id == Product.id).\
        join(User, Review.customer_id == User.id).\
        filter(Review.farmer_id == current_user.id).\
        all()
    
    # Calculate average rating for farmer
    if reviews_data:
        avg_rating = sum(review.rating for review, product, customer in reviews_data) / len(reviews_data)
        avg_rating = round(avg_rating, 1)
    else:
        avg_rating = 0
    
    return render_template('farmer_reviews.html', reviews_data=reviews_data, avg_rating=avg_rating)

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')


# Farmer orders page
@app.route('/farmer_orders')
@login_required
def farmer_orders():
    if current_user.user_type != 'farmer':
        flash('Only farmers can view orders')
        return redirect(url_for('dashboard'))
    
    # Get orders that contain products from this farmer
    orders = db.session.query(Order).\
        join(OrderItem).\
        filter(OrderItem.farmer_id == current_user.id).\
        group_by(Order.id).\
        all()
    
    # Get order items for this farmer
    order_items = OrderItem.query.filter_by(farmer_id=current_user.id).all()
    
    return render_template('farmer_orders.html', orders=orders, order_items=order_items)

# Update order status
@app.route('/update_order_status/<int:order_id>', methods=['POST'])
@login_required
def update_order_status(order_id):
    if current_user.user_type != 'farmer':
        return jsonify({'success': False, 'message': 'Only farmers can update orders'})
    
    order = Order.query.get_or_404(order_id)
    
    # Verify that this order contains products from this farmer
    farmer_order_items = OrderItem.query.filter_by(order_id=order_id, farmer_id=current_user.id).first()
    if not farmer_order_items:
        return jsonify({'success': False, 'message': 'Order not found'})
    
    new_status = request.form.get('status')
    valid_statuses = ['pending', 'accepted', 'shipped', 'delivered', 'cancelled']
    
    if new_status not in valid_statuses:
        return jsonify({'success': False, 'message': 'Invalid status'})
    
    order.status = new_status
    order.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Order status updated to {new_status}'})

# Farmer order details
@app.route('/farmer_order_details/<int:order_id>')
@login_required
def farmer_order_details(order_id):
    if current_user.user_type != 'farmer':
        flash('Only farmers can view order details')
        return redirect(url_for('dashboard'))
    
    order = Order.query.get_or_404(order_id)
    
    # Get only order items from this farmer
    order_items = OrderItem.query.filter_by(order_id=order_id, farmer_id=current_user.id).all()
    
    if not order_items:
        flash('Order not found')
        return redirect(url_for('farmer_orders'))
    
    return render_template('farmer_order_details.html', order=order, order_items=order_items)

@app.route('/order_details/<int:order_id>')
@login_required
def order_details(order_id):
    if current_user.user_type != 'customer':
        flash('Only customers can view order details')
        return redirect(url_for('dashboard'))
    
    order = Order.query.get_or_404(order_id)
    
    # Verify the order belongs to the current customer
    if order.customer_id != current_user.id:
        flash('You can only view your own orders')
        return redirect(url_for('orders'))
    
    order_items = OrderItem.query.filter_by(order_id=order_id).all()
    
    return render_template('order_details.html', order=order, order_items=order_items)



# Edit product
@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if current_user.user_type != 'farmer':
        flash('Only farmers can edit products')
        return redirect(url_for('dashboard'))
    
    product = Product.query.filter_by(id=product_id, farmer_id=current_user.id).first()
    
    if not product:
        flash('Product not found or you do not have permission to edit it')
        return redirect(url_for('my_products'))
    
    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        product.quantity = int(request.form['quantity'])
        product.category = request.form['category']
        
        db.session.commit()
        flash('Product updated successfully!')
        return redirect(url_for('my_products'))
    
    return render_template('edit_product.html', product=product)

# Delete product
@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    if current_user.user_type != 'farmer':
        flash('Only farmers can delete products')
        return redirect(url_for('dashboard'))
    
    product = Product.query.filter_by(id=product_id, farmer_id=current_user.id).first()
    
    if not product:
        flash('Product not found or you do not have permission to delete it')
        return redirect(url_for('my_products'))
    
    # Check if product has any orders
    has_orders = OrderItem.query.filter_by(product_id=product_id).first()
    
    if has_orders:
        flash('Cannot delete product that has existing orders. You can set quantity to 0 instead.')
        return redirect(url_for('my_products'))
    
    # Delete product
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully!')
    return redirect(url_for('my_products'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)