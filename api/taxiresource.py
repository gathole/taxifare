from django.conf import settings
from datetime import datetime
from django.core.cache import cache

from tastypie.resources import ModelResource
from tastypie.resources import Resource
from tastypie import fields
from tastypie.authentication import BasicAuthentication
from tastypie.authorization import ReadOnlyAuthorization

from taxi.models import *
from taxi.cache_key import *
from api.dict_obj import DictObject


class CityResource(ModelResource):
    class Meta:
        queryset = City.objects.all()
        include_resource_uri = False
        excludes = ['id']
        allowed_methods = ['get']
        resource_name = 'city'
        authorization= ReadOnlyAuthorization()
        authentication= BasicAuthentication()
          
class FareResource(Resource):
    base_fare		= fields.FloatField(attribute="base_fare", null=True)
    base_km			= fields.FloatField(attribute="base_km", null=True)
    extra_km_fare	= fields.FloatField(attribute="extra_km_fare", null=True)
    flat_fare		= fields.FloatField(attribute="flat_fare", null=True)
    car_type		= fields.CharField(attribute="car_type", null=True)
    trip_type		= fields.CharField(attribute="trip_type", null=True)
    
    class Meta:
        include_resource_uri = False
        allowed_methods = ['get']
        resource_name = 'fare'
        object_class = DictObject       
        authorization= ReadOnlyAuthorization()
        authentication= BasicAuthentication()

    def get_city(self, name):
        KEY = CITY_KEY.format(name)
        city = cache.get(KEY, None)
        if city is None:
            try:
                city = City.objects.get(name=name)
                cache.set(KEY, city, settings.CACHE_TIMEOUT)
            except City.DoesNotExist:
                city = None        
        return city

    def get_trip(self, type): 
        KEY = TRIP_KEY.format(type)
        trip = cache.get(KEY, None)   
        if trip is None:    
            try:
                trip = TripType.objects.get(type=type)                
                cache.set(KEY, trip, settings.CACHE_TIMEOUT)
            except TripType.DoesNotExist:
                trip = None
        return trip

    def get_car(self, model):
        KEY = CAR_KEY.format(model)
        car = cache.get(KEY, None)   
        if car is None:   
            try:
                car = Car.objects.get(model=model)          
                cache.set(KEY, car, settings.CACHE_TIMEOUT)
            except Car.DoesNotExist:
                car = None
        return car

    def extra_charge(self, time, outside, fare_variation):
        extra_charge = 0.0
        try:
            hours = int(time.split(':')[0])
            assert 0<= hours <=23
        except Exception as e:
            hours = datetime.now().hour

        if hours >= settings.START_NIGHT or hours <= settings.END_NIGHT:
            extra_charge += fare_variation.outside_city
        if outside:
            extra_charge += fare_variation.outside_city
        
        return extra_charge

    def discount(self, date):
        try:
            date = datetime.strptime(date, "%Y-%m-%d")
        except:
            date = datetime.now()
        try:
            offer = Offer.objects.get(date=date.date())
            print offer
            return offer.discount_percent
        except:
            pass
        return 0.0

    def get_object_list(self, request):
        
        object_list = list()

        from_location = request.REQUEST.get('from_location', None)
        to_location = request.REQUEST.get('to_location', None)
        
        city_name = request.REQUEST.get('city', None)
        trip_type = request.REQUEST.get('trip_type', None)
        car_type = request.REQUEST.get('car_type', None)

        time = request.REQUEST.get('time', None)
        date = request.REQUEST.get('date', None)
        outside = request.REQUEST.get('outside', None)

        city = self.get_city(city_name)
        trip_obj = self.get_trip(trip_type)
        car = self.get_car(car_type)

        try:
            # Convert to True or False
            # if 'true' is given first make it 'True' and then convert
            outside = eval(outside.title())
        except:
            outside = False        

        if city and trip_obj:
            is_outside_trip = (trip_type.lower() == 'outstation') or outside
            extra_charges = self.extra_charge(time, is_outside_trip, city.farevariation)
            dicount = self.discount(date)
        
            fare = {'base_fare': city.base_fare, 'base_km': city.base_km, 'extra_km_fare': city.extra_km_fare}
            if car:
                total_extra_charges = extra_charges + car.fare_percent
                obj = self.get_fare_details(fare, total_extra_charges/100.0, dicount/100.0)
                object_list.append(obj)

                if not is_outside_trip:
                    KEY = CITY_TRIP_KEY.format(city.id, trip_obj.id)
                    city_trip = cache.get(KEY, None)
                    if city_trip is None:
                        city_trip = CityTrip.objects.filter(city=city, trip_type=trip_obj) 
                        cache.set(KEY, city_trip, settings.CACHE_TIMEOUT)
                    for ct in city_trip:
                        obj = DictObject()
                        obj.flat_fare = ct.flat_fare + ct.flat_fare*total_extra_charges/100.0 - ct.flat_fare*dicount/100.0
                        object_list.append(obj)
            else:
                cars = cache.get(ALL_CAR, None)
                if cars is None:
                    cars = Car.objects.all()
                    cache.set(ALL_CAR, cars, settings.CACHE_TIMEOUT)
                for car in cars:
                    total_extra_charges = extra_charges + car.fare_percent
                    obj = self.get_fare_details(fare, total_extra_charges/100.0, dicount/100.0)
                    obj.car_type = car.model
                    object_list.append(obj)

        return object_list

    def get_fare_details(self, fare, extra_charges=0.0, dicount=0.0):
        obj = DictObject()
        obj.base_fare       = fare['base_fare'] + fare['base_fare']*extra_charges - fare['base_fare']*dicount
        obj.base_km         = fare['base_km'] + fare['base_km']*extra_charges - fare['base_km']*dicount
        obj.extra_km_fare   = fare['extra_km_fare'] + fare['extra_km_fare']*extra_charges - fare['extra_km_fare']*dicount
        return obj
         
    def obj_get_list(self, bundle, **kwargs):    	
        request = bundle.request
        return self.get_object_list(request)
        
    def clean_bundle(self, bundle):
    	null_keys = [k for k, v in bundle.data.items() if v is None ]
    	for key in null_keys:
    		del bundle.data[key]

    def dehydrate(self, bundle):
        self.clean_bundle(bundle)
        return bundle         


        