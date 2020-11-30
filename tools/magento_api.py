# -*- coding: utf-8 -*-
#################################################################################
# Author	  : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#
#	Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#
##########################################################################
true =True
fale=False
none=None


import pprint
import urllib
from urllib.parse import  quote_plus
import json
import requests
import logging
from datetime import datetime, timedelta


pp = pprint.PrettyPrinter(indent=1, width=80, depth=None, stream=None)
pp.pprint({})
_logger = logging.getLogger(__name__)


class MageError(Exception):
		pass

def p_decorate(func):
	def func_wrapper(self,*args, **kwargs):
		response=None
		res = dict(
			data=None,
			message=''
		)
		try:
			response  =func(self,*args, **kwargs)
			if self.debug:
				_logger.info("response===> %s"%(response))
		except Exception as e:
			res['message']+=str(e)
		if type(response)==requests.models.Response :

			if response.status_code > 201:
				content = response.content
				code = response.status_code
				if 'oauth_problem'.encode() in content:
					print ("###"+content)
				res['message']+='API returned %s response: %s' % (code, content)
			else:
				try:
					res['data'] = response.json()#pprint.pformat(response.json())
				except Exception as e:
					res['message']+=response.content
		if self.debug:
			_logger.info("res===> %s"%(res))
		return res
	return func_wrapper


class Magento2(object):


	def __init__(self, *args, **kwargs):
		self.username = kwargs.get('username')
		self.password = kwargs.get('password')
		self.base_uri = kwargs.get('base_uri')
		self.store_code = kwargs.get('store_code','default')
		self.oauth_token  = kwargs.get('oauth_token')
		self.debug  = kwargs.get('debug', False)
		if kwargs.get('base_uri'):
			self.rest_uri = self._get_rest_uri()
		if self.rest_uri and kwargs.get('username') and kwargs.get('password'):
			oauth_token_res = self._get_oauth_token()
			self.oauth_token = oauth_token_res.get('data')


	def _get_rest_uri(self):
		rest = '{base}/index.php/rest/{store_code}/V1'.format(base=self.base_uri,store_code=self.store_code)
		return rest


	def _get_oauth_uri(self):
		oauth = '{base}/integration/admin/token'.format(base=self.rest_uri)
		return oauth


	@p_decorate
	def _get_data(self,url,params=None,headers={}):
		headers.update({
			'Content-Type' : 'application/json',
			'Authorization' : 'Bearer %s'%(self.oauth_token),
		})
		params = params or dict()
		res =   requests.get(
			url,
			params=params,
			headers=headers,verify=False
		)
		return res


	@p_decorate
	def _post_data(self,url,data=None,files=None,params={},headers=None):
		if headers==None:
			headers={
				'Content-Type' : 'application/json',
				'Authorization' : 'Bearer %s'%(self.oauth_token),
			}
		data = data or dict()

		res= requests.post(
			url,
			data=data,
			params=params,
			files=files,
			headers=headers,verify=False
		)
		return res

		

	@p_decorate
	def _del_data(self,url,data=None,params={},headers={}):
		data = data or dict()
		res= requests.delete(
			url,
			data=data,
			params=params,
			headers=headers,verify=False
		)
		return res


	@p_decorate
	def _put_data(self,url,data=None,params={},headers=None):
		if headers==None:
			headers={
				'Content-Type' : 'application/json',
				'Authorization' : 'Bearer %s'%(self.oauth_token),
			}
		data = data or dict()
		res= requests.put(
			url,
			data=data,
			params=params,
			headers=headers,verify=False
		)
		return res


	def _get_oauth_token(self):
		headers= {'Content-Type' : 'application/json'}
		data = dict(
		username=self.username,
		password=self.password,

		)
		endpoint = self._get_oauth_uri()
		return self._post_data(endpoint,data,headers,headers={})


	def get_store_configs(self,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/store/storeConfigs'.format(rest_v1=self.rest_uri)
		return self._get_data(endpoint,params)


	def get_categories(self,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/categories'.format(rest_v1=self.rest_uri)
		return self._get_data(endpoint,params)
	def post_categories(self,data=None,category_id=None,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/categories'.format(rest_v1=self.rest_uri)
		if category_id:
			endpoint+='/%s'%(category_id)
			return self._put_data(endpoint,data=json.dumps(dict(category=data)),params=params)
		return self._post_data(endpoint,data=json.dumps(dict(category=data)),params=params)

	def move_category(self,data=None,category_id=None,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/categories'.format(rest_v1=self.rest_uri)
		if category_id:
			endpoint+='/%s'%(category_id)+'/move'
			return self._put_data(endpoint,data=json.dumps(data),params=params)

	def get_products_attribute_sets(self, attribute_set_id=None, params=None,):
		params = params or dict()
		endpoint ='{rest_v1}/products/attribute-sets'.format(rest_v1=self.rest_uri)
		if attribute_set_id:
			endpoint+='/%s/attributes'%(attribute_set_id)
		elif not len(params.keys()):
			endpoint+='/sets/list'
			params['searchCriteria']= dict(sortOrders='asc')
		return self._get_data(endpoint,params)


	def post_products_attributes(self,data,attribute_code=None,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/products/attributes'.format(rest_v1=self.rest_uri)
		# return data
		if attribute_code:
			endpoint+='/%s/options'%(attribute_code)
			return self._post_data(endpoint,data=json.dumps(dict(option=data)),params=params)
		return self._post_data(endpoint,data=json.dumps(dict(attribute=data)),params=params)


	def get_attributes(self,attribute_code=None,params=None):
		params =  params or dict()
		endpoint ='{rest_v1}/products/attributes'.format(rest_v1=self.rest_uri)
		if attribute_code:
			endpoint ='{endpoint}/{attribute_code}/options'.format(
					 endpoint=endpoint,attribute_code=attribute_code
				)
		if not len(params.keys()):
			params['searchCriteria']= dict(sortOrders='asc')
		return self._get_data(endpoint,params)


	def get_products_media(self,sku,entry_id=None,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/products'.format(rest_v1=self.rest_uri)
		if sku:
			endpoint+='/%s/media'%( quote_plus(sku))
			if entry_id:
				pass
				# endpoint+='/%s'%(entry_id)
		return self._get_data(endpoint,params)


	def post_products_media(self,sku,data,entry_id=None,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/products'.format(rest_v1=self.rest_uri)
		if sku:
			endpoint+='/%s/media'%( quote_plus(sku))
			if entry_id:
				endpoint+='/%s'%(entry_id)
		return self._post_data(endpoint,data=json.dumps(dict(entry=data)),params=params)
	def get_products_children(self,sku,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/configurable-products/{sku}/children'.format(rest_v1=self.rest_uri,sku=sku)
		if not len(params.keys()):
			params['searchCriteria']= dict(sortOrders='asc')
		return self._get_data(endpoint,params)

	def get_products(self,sku=None,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/products'.format(rest_v1=self.rest_uri)

		if sku:
			endpoint+='/%s'%(quote_plus(sku))
		elif not len(params.keys()):
			params['searchCriteria']= dict(sortOrders='asc')
		return self._get_data(endpoint,params)


	def post_products(self,data,sku=None,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/products'.format(rest_v1=self.rest_uri)
		if sku:
			endpoint+='/%s'%(quote_plus(sku))
			return self._put_data(endpoint,data=json.dumps(dict(product=data)),params=params)
		return self._post_data(endpoint,data=json.dumps(dict(product=data)),params=params)


	def get_customers(self,c_id=None,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/customers'.format(rest_v1=self.rest_uri)
		endpoint+='/search'
		if c_id:
			endpoint+='/%s'%(c_id)
		elif not len(params.keys()):
			params['searchCriteria']= dict(sortOrders='asc')
		return self._get_data(endpoint,params)


	def get_orders(self,order_id=None,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/orders'.format(rest_v1=self.rest_uri)
		if order_id:
			endpoint+='/%s'%(order_id)
		elif not len(params.keys()):
			params['searchCriteria']= dict(sortOrders='asc')
		return self._get_data(endpoint,params)

	def cancel_order(self,order_id,params=None):
			params = params or dict()
			endpoint = '{rest_v1}/orders/{order_id}/cancel'.format(rest_v1=self.rest_uri,order_id=order_id)
			return self._post_data(endpoint,params=params)


	def post_orders_invoice(self,order_id,data,params=None):
			params = params or dict()
			endpoint ='{rest_v1}/order/{order_id}/invoice'.format(rest_v1=self.rest_uri,order_id=order_id)
			return self._post_data(endpoint,data=json.dumps(data),params=params)


	def post_orders_ship(self,order_id,data,params=None):
		params = params or dict()
		endpoint ='{rest_v1}/order/{order_id}/ship'.format(rest_v1=self.rest_uri,order_id=order_id)
		return self._post_data(endpoint,data=json.dumps(data),params=params)


	def get_configurable_products(self,sku,params=None,):
		params = params or dict()
		endpoint ='{rest_v1}/configurable-products/{sku}/options/all'.format(rest_v1=self.rest_uri,sku= quote_plus(sku))
		return self._get_data(endpoint,params)

if __name__ =='__main__':
	pass
