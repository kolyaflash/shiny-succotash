Development
===========================================


Service/Provider
-----------------------

1.

	In Service request, handling happens in service method. Service method can request provider as a tool to use,
	but not like delegate them execution flow.

2.

	Provider selection strategy can be different for different services.

3.
	If provider fails, we mark it as unreliable and client needs to repeat a request (that probably
	will be executed using another provider).

4.
	Services expected to not decide which Provider to use. Though, they can ask for a provider that supports
	all needed methods. And they can ask for some exact provider in some cases.


5.
	We must always use the same provider for some requests type. E.g. client wants to create domain name,
	so we use Namecheap to register his .com domain and than must use Namecheap to manage it.
	For .lg.ua domain it would be another domain registrant, but the same flow.


Service gateway goals:
-----------------------

*
	**provide highly available service.** for example, we have service for currency exchange rates (Service).
	so when the request to get latest exchange rates (Method) came in, and fixer.io (Provider) is currently
	down, we, instead of return error to client, trying to get rates from (currencylayer.com).

*
	**cost efficiency.** depending on a requester party, we could be in favour of provider A rather than
	provider B, because calling provider A is cheaper because of, let's say, requester's country of residency.
	Same time, it can be cheaper to call some provider A for particular task (e.g. convert currency), but
	expensive for another one (e.g. get all currency rates).

*
	**apply charges for requesting service gateway.** but the idea is to charge user independently of
	used provider. so *cost efficiency* matters, because saved costs is our revenue.

*
	**incapsulation.** Provides the optimal API for each client.
	Simplifies the client by moving logic for calling multiple services from the client to API gateway.
	Translates from a “standard” public web-friendly API protocol to whatever protocols are used internally. Etc.


*
	**be analysable.** we must know as much metrics of services usage as possible. also, we must be able
	to easily find a particular request to find out about e.g. it's cost, source and destination.



Services reliability
-----------------------

Services/providers states must be stored in some global storage. Probably in Cental Config.
TODO: think more.
