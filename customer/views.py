from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils.encoding import force_text, force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views import View
from django.views.generic import ListView, CreateView

from customer.forms import CustomerSignUpForm, CustomerFeedbackForm, CustomerProfileForm, CustomerForm
from customer.models import Customer, CustomerFeedback
from salonist.tokens import account_activation_token
from service.forms import BookingPaymentForm, AppointmentForm
from service.models import Service, Booking, Apprenticeship, BookingPayment, Appointment
from store.forms import OrderPaymentForm
from store.models import Order, Product, OrderItem, OrderPayment, Wishlist
from user.decorators import customer_required
from user.models import CustomUser
from utils.utils import generate_key


# from mpesa_api.core.mpesa import Mpesa


class Home(ListView):
    model = Service
    template_name = "customer/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.request.user.customer
        context['booking_transactions'] = BookingPayment.objects.filter(customer=customer)
        context['order_transactions'] = OrderPayment.objects.filter(customer=customer)
        print(f"These are payment orders {context['order_transactions']}")
        context['appointments'] = Appointment.objects.filter(customer=customer)
        context['bookings'] = Booking.objects.filter(customer=customer)
        order = Order.objects.filter(customer=customer)
        context['orders'] = order
        context['order'] = Order.objects.filter(customer=customer, completed=False).first()
        return context


class ApprenticeshipListView(ListView):
    model = Apprenticeship
    template_name = "customer/forms/apprenticeship.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['object_list'] = self.object_list.filter(is_active=True, closed=False, is_archived=False)
        return context


class BookingListView(ListView):
    model = Booking
    template_name = "customer/forms/booking.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.request.user.customer
        context['object'] = self.object_list.filter(customer=customer, is_active=False).first()
        return context


class OrderListView(ListView):
    model = Order
    template_name = "customer/forms/order.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.request.user.customer
        context['object_list'] = self.object_list.filter(customer=customer, is_active=True)
        return context


def login(request):
    if request.method == "POST":
        remember = request.POST.get('remember')
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if not remember == "remember-me":
            request.session.set_expiry(0)
        if user is not None:
            if not user.is_active and user.is_customer and not user.is_archived:
                if user.is_verified:
                    messages.info(request,
                                  "your email is verified, but your account is "
                                  "inactive. Check your mail for notification.")
                else:
                    messages.info(request,
                                  "your email is not verified, verify your email.")
            elif user.is_active and user.is_customer and not user.is_archived:
                if user.is_verified:
                    auth_login(request, user)
                    user = request.user.get_full_name
                    messages.success(request, f"Hi {user}, welcome to Ashley's Salon.")
                    try:
                        if 'add_to_cart' in request.GET.get('next', 'customer:index'):
                            return redirect('customer:index')
                        else:
                            return redirect(request.GET.get('next', 'customer:index'))
                    except (NoReverseMatch, ImproperlyConfigured):
                        return redirect("customer:index")
                else:
                    messages.info(request,
                                  "you've registered, but your email is not verified, verify your email and try again.")
            else:
                messages.info(request, f"Hi {user.get_full_name}, "
                                       f"you can't login here, this login page is for Customers only.")
                logout(request)
                try:
                    return redirect(request.GET.get('next', ''))
                except (NoReverseMatch, ImproperlyConfigured):
                    return redirect("customer:login")
        else:
            messages.info(request, "your email or password is incorrect. Please check.")
            try:
                return redirect(request.GET.get('next', ''))
            except (NoReverseMatch, ImproperlyConfigured):
                return redirect("customer:login")
    return render(request, 'customer/accounts/login.html')


class CustomerSignUpView(CreateView):
    form_class = CustomerSignUpForm
    template_name = "customer/accounts/register.html"

    def get_form_kwargs(self):
        kwargs = super(CustomerSignUpView, self).get_form_kwargs()
        return kwargs

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_invalid(self, form):
        context = {
            'info': "Please correct errors below",
            'form': form.errors,
        }
        return JsonResponse(context, status=200)

    def form_valid(self, form):
        name = form.instance.first_name
        last = form.instance.last_name
        username = form.instance.email
        username = username.lower()
        form.instance.email = username
        if '@gmail.com' in username:
            username = username.replace('@gmail.com', '')
        elif '@yahoo.com' in username:
            username = username.replace('@yahoo.com', '')
        elif '@hotmail.com' in username:
            username = username.replace('@hotmail.com', '')
        elif '@live.com' in username:
            username = username.replace('@live.com', '')
        elif '@msn.com' in username:
            username = username.replace('@msn.com', '')
        elif '@passport.com' in username:
            username = username.replace('@passport.com', '')
        elif '@outlook.com' in username:
            username = username.replace('@outlook.com', '')
        form.instance.username = username
        user = form.save(commit=False)
        user.is_active = True
        user.save()
        # current_site = get_current_site(self.request)
        # to_email = form.cleaned_data.get('email')
        # subject = f"Ashley's Salon Customer Email Verification."
        # msg_plain = render_to_string('customer/emails/email.txt', {'user_name': user.get_full_name, })
        # msg_html = render_to_string('customer/emails/account_activation_email.html', {
        #     'user': user,
        #     'domain': current_site.domain,
        #     'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        #     'token': account_activation_token.make_token(user),
        # })
        # send_mail(subject, msg_plain, "Ashley's Salon", [to_email], html_message=msg_html)
        data = {
            'status': True,
            'message': f"Hi {name} {last}, your account has been created successfully  wait for approval.",
            'redirect': reverse('customer:login')
        }
        return JsonResponse(data)


class VerifyEmail(View):

    def get(self, request, uidb64, token, *args, **kwargs):
        try:
            uid = force_text(urlsafe_base64_decode(uidb64))
            user = Customer.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError):
            user = None
        data = {}
        if user is not None and account_activation_token.check_token(user, token):
            if user.is_verified:
                messages.info(request, "you've already confirmed your email.")
                data['message'] = "you've already confirmed your email."
            elif not user.is_verified:
                user.is_verified = True
                user.save()
                data['message'] = "You've successfully verified your email. use your email to login"
        else:
            data['message'] = 'The confirmation link was invalid, possibly because it has already been used.'
        return JsonResponse(data)


def log_out(request):
    logout(request)
    messages.info(request, f"You've logged out successfully.")
    return redirect('customer:index')


def profile(request):
    data = {}
    if request.method == "POST":
        p_form = CustomerProfileForm(request.POST, request.FILES, instance=request.user.customer.customerprofile)
        form = CustomerForm(request.POST, instance=request.user.customer)
        if form.is_valid() and p_form.is_valid():
            form.save()
            p_form.save()
            data['message'] = "Your Profile has been updated!"
            return JsonResponse(data)
        else:
            data['info'] = "sorry, this form is invalid!"
            data['form'] = form.errors
            data['p_form'] = p_form.errors
            print(p_form)
            print(form)
            return JsonResponse(data)
    else:
        p_form = CustomerProfileForm(instance=request.user.customer.customerprofile)
        form = CustomerForm(request.POST, instance=request.user.customer)

    data['form'] = form.errors
    data['p_form'] = p_form.errors
    return JsonResponse(data)


def profile_main(request):
    if request.method == "POST":
        p_form = CustomerProfileForm(request.POST, request.FILES, instance=request.user.customer.customerprofile)
        form = CustomerForm(request.POST, instance=request.user.customer)
    else:
        p_form = CustomerProfileForm(instance=request.user.customer.customerprofile)
        form = CustomerForm(instance=request.user.customer)
    customer = request.user.customer
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    context = {
        'p_form': p_form,
        'form': form,
        'order': order
    }
    return render(request, 'customer/accounts/profile.html', context)


def faq(request):  # Not Done
    customer = request.user.customer
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    context = {'order': order}
    return render(request, 'customer/faq.html', context)


def change_password(request):
    context = {}
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important!
            messages.success(request, 'Your password was successfully updated!')
            context['message'] = 'Your password was successfully updated!'
            return JsonResponse(context)
        else:
            context['info'] = 'Please correct the errors below.'
    else:
        form = PasswordChangeForm(request.user)
    context['form'] = form.errors
    return JsonResponse(context)


def password_change(request):
    form = PasswordChangeForm(request.user)
    customer = request.user.customer
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    return render(request, 'customer/accounts/change-password.html', {'form': form, 'order': order})


def feedback(request):
    customer = request.user.customer
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    form = CustomerFeedbackForm
    # if request.method == "POST":
    #     form = CustomerFeedbackForm(request.POST)
    #     if form.is_valid():
    #         instance = form.save(commit=False)
    #         instance.customer = request.user.customer
    #         admin = CustomUser.objects.filter(is_staff=True, is_superuser=True, is_active=True).first()
    #         instance.admin = admin
    #         if CustomerFeedback.objects.filter(subject=instance.subject, message=instance.message,
    #                                            customer=instance.customer, admin=admin).exists():
    #             messages.info(request, "You've already sent this feedback, thank you.")
    #         elif CustomerFeedback.objects.filter(subject=instance.subject, customer=instance.customer,
    #                                              admin=admin).exists():
    #             messages.info(request, "You've already sent this feedback, thank you.")
    #         elif CustomerFeedback.objects.filter(message=instance.message, customer=instance.customer,
    #                                              admin=admin).exists():
    #             messages.info(request, "You've already sent this feedback, thank you.")
    #         else:
    #             instance.save()
    #             messages.success(request, "Feedback has been sent. Thank you")
    return render(request, 'customer/accounts/feedback.html', {'order': order, 'form': form})


def feedback_api(request):
    data = {}
    if request.method == "POST":
        form = CustomerFeedbackForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.user = request.user.customer
            admin = CustomUser.objects.filter(is_staff=True, is_superuser=True, is_active=True).first()
            instance.admin = admin
            if CustomerFeedback.objects.filter(subject=instance.subject, message=instance.message,
                                               user=instance.user, admin=admin).exists():
                data['info'] = "You've already sent this feedback, thank you."
                data['form'] = {'subject': "feedback with this title already exists"}
                data['form'] = {'message': "feedback with this message already exists"}
            elif CustomerFeedback.objects.filter(subject=instance.subject, user=instance.user,
                                                 admin=admin).exists():
                data['info'] = "You've already sent this feedback, thank you."
                data['form'] = {'subject': "feedback with this title already exists"}
            elif CustomerFeedback.objects.filter(message=instance.message, user=instance.user,
                                                 admin=admin).exists():
                data['info'] = "You've already sent this feedback, thank you."
                data['form'] = {'message': "feedback with this message already exists"}
            else:
                instance.save()
                data['message'] = "Feedback has been sent. Thank you"
        else:
            data['info'] = "sorry, Form is invalid"
            data['form'] = form.errors
    return JsonResponse(data)


def add_to_cart(request, slug):
    data = {}
    customer = request.user.customer
    product = Product.objects.filter(slug=slug).first()
    if Wishlist.objects.filter(customer=customer, product=product).exists():
        instance = Wishlist.objects.get(customer=customer, product=product)
        instance.cart = True
        instance.save()
    if Order.objects.filter(customer=customer, is_active=True, completed=False).exists():
        order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
        if OrderItem.objects.filter(order=order, product=product).exists():
            order_item = OrderItem.objects.get(order=order, product=product)
            quantity = order_item.quantity + 1
            if quantity <= product.quantity:
                order_item.quantity = quantity
                order_item.save()
                data['message'] = f"{quantity} {product.name} has been added to cart"
            else:
                data['info'] = f"{quantity} {product.name} are not available we only have {product.quantity} remaining."
        else:
            if product.quantity >= 1:
                OrderItem.objects.create(order=order, product=product, quantity=1)
                data['message'] = f"1 {product.name} has been added to cart"
            else:
                data['info'] = f"Sorry this item is out of stock"
    else:
        order = Order.objects.create(customer=customer, is_active=True, completed=False,
                                     transaction_id=generate_key(6, 6))
        if product.quantity >= 1:
            OrderItem.objects.create(order=order, product=product, quantity=1)
            data['message'] = f"1 {product.name} has been added to cart"
        else:
            data['info'] = f"Sorry this item is out of stock"
    return JsonResponse(data)


def cart_list(request):
    data = {}
    order = Order.objects.filter(customer=request.user.customer, is_active=True, completed=False).first()
    data['object_list'] = order.orderitem_set.all()
    data['order'] = order
    return render(request, 'customer/accounts/cart.html', data)


def wishlist_list(request):
    data = {}
    wishlist = Wishlist.objects.filter(customer=request.user.customer)
    data['object_list'] = wishlist
    customer = request.user.customer
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    data['order'] = order
    return render(request, 'customer/accounts/wishlist.html', data)


def remove_from_cart(request, slug):
    data = {}
    customer = request.user.customer
    product = Product.objects.filter(slug=slug).first()
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    item = OrderItem.objects.filter(order=order, product=product).first()
    item.delete()
    data['message'] = f"{product.name} has been removed from cart successfully"
    return JsonResponse(data)


def decrease_quantity(request, slug):
    data = {}
    customer = request.user.customer
    product = Product.objects.filter(slug=slug).first()
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    item = OrderItem.objects.filter(order=order, product=product).first()
    quantity = item.quantity - 1
    if quantity >= 1:
        item.quantity = quantity
        item.save()
        data['message'] = f"{product.name} quantity has been decreased to {quantity}"
    else:
        item.delete()
        data['message'] = f"{product.name} has been removed from cart successfully."
    return JsonResponse(data)


def increase_quantity(request, slug):
    data = {}
    customer = request.user.customer
    product = Product.objects.filter(slug=slug).first()
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    item = OrderItem.objects.filter(order=order, product=product).first()
    quantity = item.quantity + 1
    if product.quantity >= quantity:
        item.quantity = quantity
        item.save()
        data['message'] = f"{product.name} quantity has been increased to {quantity}"
    else:
        data['info'] = f"{quantity} {product.name} are not available we only have {product.quantity} remaining."
    return JsonResponse(data)


def clear_cart(request):
    data = {}
    customer = request.user.customer
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    order.is_active = False
    order.save()
    data['message'] = "Cart has been cleared successfully."
    return JsonResponse(data)


def checkout(request):
    data = {}
    try:
        customer = request.user.customer
        order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
        data['order'] = order
        data['form'] = OrderPaymentForm
        data['object_list'] = order.orderitem_set.all()
        products = []
        for item in order.orderitem_set.all():
            product = {
                'quantity': item.quantity,
                'name': item.product.name,
                'slug': item.product.slug,
            }
            products.append(product)
        print(products)
        for item in products:
            product = Product.objects.filter(slug=item['slug']).first()
            if product.quantity >= item['quantity']:
                print(f"{product.quantity} >= {item['quantity']}")
                print("Everything is fine products exists")
            else:
                instance = OrderItem.objects.get(order=order, product=product)
                if product.quantity > 0:
                    instance.quantity = product.quantity
                    instance.save()
                else:
                    instance.delete()
    except AttributeError:
        pass
    return render(request, 'customer/forms/checkout.html', data)


def checkout_pay(request):
    data = {}
    customer = request.user.customer
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    if request.method == "POST":
        form = OrderPaymentForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            mpesa = instance.mpesa
            if len(mpesa) == 10:
                if instance.amount == order.get_cart_total:
                    instance.order = order
                    instance.transaction_id = generate_key(8, 8)
                    instance.save()
                    data['message'] = "Payment has been done successfully"
                    order.completed = True
                    order.save()
                    items = order.orderitem_set.all()
                    for item in items:
                        product = Product.objects.filter(id=item.product.id).first()
                        quantity = product.quantity - item.quantity
                        product.quantity = quantity
                        product.save()
                else:
                    data['info'] = f"amount sent is {instance.amount} but amount required is {order.get_cart_total}"
            else:
                data['mpesa'] = "Enter valid mpesa code"
        else:
            data['info'] = "This form is invalid"
            data['form'] = form.errors
    return JsonResponse(data)


def order_list(request):
    data = {}
    customer = request.user.customer
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    data['order'] = order
    return render(request, 'customer/forms/checkout.html', data)


def book_hairstyle(request, service_id):
    data = {}
    customer = request.user.customer
    service = Service.objects.filter(id=service_id).first()
    if Booking.objects.filter(customer=customer, is_active=False).exists():
        data['info'] = f"Hi {customer.get_full_name}, you've an ongoing booking"
    else:
        Booking.objects.create(customer=customer, service=service, is_active=False)
        data['info'] = f"{service.name}, has been booked successfully proceed to payment."
    return JsonResponse(data)


def booking_payment(request, service_id):
    data = {}
    customer = request.user.customer
    if request.method == "POST":
        form = BookingPaymentForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.booking = Booking.objects.get(id=service_id)
            mpesa = instance.mpesa
            if len(mpesa) == 10:
                if instance.amount == instance.booking.service.price:
                    if BookingPayment.objects.filter(booking=instance.booking, customer=customer).exists():
                        instance.save()
                        instance = instance.booking
                        instance.is_paid = True
                        instance.save()
                        data['message'] = f"Hi {customer.get_full_name}, payment has been sent successfully."
                    else:
                        data['info'] = f"You've already made payment for {instance.booking.transaction_id} booking"
                else:
                    data[
                        'info'] = f"amount sent is {instance.amount} but amount required is {instance.booking.service.price}"
            else:
                data['mpesa'] = "Enter valid mpesa code"
        else:
            data['info'] = "This form is invalid"
            data['form'] = form.errors
    return JsonResponse(data)


def booking_checkout(request):
    data = {}
    customer = request.user.customer
    data['object'] = Booking.objects.filter(customer=customer, is_active=False).first()
    data['form'] = BookingPaymentForm
    return render(request, 'customer/forms/booking-checkout.html', data)


def customer_logout(request):
    logout(request)
    messages.info(request, "You've logged out successfully")
    return redirect('home:index')


def add_to_wishlist(request, slug):
    customer = request.user.customer
    product = Product.objects.filter(slug=slug).first()
    order = Order.objects.filter(customer=customer, is_active=True, completed=False).first()
    if OrderItem.objects.filter(order=order, product=product).exists():
        order_item = OrderItem.objects.filter(order=order, product=product).first()
        messages.info(request, f"you have {order_item.quantity} {product.name} in your cart.")
    else:
        if Wishlist.objects.filter(customer=customer, product=product).exists():
            messages.info(request, f"{product.name} has already been added to wishlist.")
        else:
            Wishlist.objects.create(customer=customer, product=product)
            messages.success(request, f"{product.name} has been added to wishlist successfully.")
    return redirect('home:index')


def remove_from_wishlist(request, slug):
    customer = request.user.customer
    product = Product.objects.filter(slug=slug).first()
    if Wishlist.objects.filter(customer=customer, product=product).exists():
        item = Wishlist.objects.filter(customer=customer, product=product).first()
        item.delete()
        messages.success(request, f"{product.name} has already been removed from wishlist.")
    else:
        messages.info(request, f"{product.name} is not in wishlist.")
    return redirect('customer:wishlist_list')


def add_billing(request):
    return render(request, 'customer/forms/add-billing.html')


#
#
# def booking(request):
#     return render(request, 'customer/tables/booking.html')


def add_booking(request, slug):
    customer = request.user.customer
    service = Service.objects.filter(id=slug).first()
    if Booking.objects.filter(customer=customer, is_active=False).exists():
        booking = Booking.objects.filter(customer=customer, is_active=False).first()
        messages.info(request, f"booking for {booking.service.name} already in progress.")
    else:
        booking = Booking.objects.create(customer=customer, service=service,
                                         transaction_id=generate_key(6, 6), is_active=False, is_paid=False)
        messages.success(request, f"{booking.service.name}, has been booked successfully please, proceed to payment.")
    return redirect('home:index')


def book_appointment(request):
    context = {}
    if request.method == "POST":
        form = AppointmentForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            case_1 = Appointment.objects.filter(date__lte=instance.date,
                                                stop_date__gte=instance.date).exists()

            # case 2: a room is booked before the requested check_out date and check_out date is after requested
            # check_out date
            case_2 = Appointment.objects.filter(date__lte=instance.stop_date,
                                                stop_date__gte=instance.stop_date).exists()

            case_3 = Appointment.objects.filter(date__gte=instance.date,
                                                stop_date__lte=instance.stop_date).exists()
            if instance.date >= instance.check_in:
                # if either of these is true, abort and render the error
                if case_1 or case_2 or case_3:
                    context['info'] = f"Sorry, An appointment exists in selected dates"
                else:
                    instance.save()
                    context['message'] = f"Appointment has been set successfully."
            else:
                context['info'] = "Sorry Stop time has to be future of Start time not past"
    return JsonResponse(context)



def generate_pending_donation_pdf(request):
    """Generate pdf."""
    # Model data
    user = request.user.id
    fund = funds.objects.filter(sponsor_id=user, status="P").order_by('-timestamp')
    # Rendered
    html_string = render_to_string('sponsor/pending_donation_pdf.html', {'funds': fund})
    html = HTML(string=html_string)
    result = html.write_pdf()

    # Creating http response
    response = HttpResponse(result, content_type='application/pdf;')
    response['Content-Disposition'] = 'inline; filename=pending_donation.pdf'
    return response
