/*
 * Copyright 2011-2012 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */
/*global define require console setTimeout window*/

define([
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/_base/window",
	"dojo/query",
	"dojo/request/xhr",
	"dojo/_base/xhr",
	"dojo/Deferred",
	"dojo/json",
	"dojo/topic",
	"dojo/cookie",
	"dojo/sniff",
	"dijit/Dialog",
	"dijit/TitlePane",
	"dojox/timing/_base",
	"dojox/html/styles",
	"dojox/html/entities",
	"umc/widgets/ContainerWidget",
	"umc/widgets/ConfirmDialog",
	"umc/widgets/Text",
	"umc/i18n!umc/app"
], function(lang, array, _window, query, xhr, basexhr, Deferred, json, topic, cookie, has, Dialog, TitlePane, timing, styles, entities, ContainerWidget, ConfirmDialog, Text, _) {

	// in order to break circular dependencies (umc.tools needs a Widget and
	// the Widget needs umc/tools), we define umc/dialog as an empty object and
	// require it explicitely
	var dialog = {
		login: function() {
			return new Deferred();
		},
		notify: function() {},
		alert: function() {},
		centerAlertDialog: function() {}
	};
	require(['umc/dialog'], function(_dialog) {
		// register the real umc/dialog module in the local scope
		dialog = _dialog;
	});

	// define umc/tools
	var tools = {};
	lang.mixin(tools, {
		_status: {
			username: null,
			hostname: '',
			domainname: '',
			overview: true,
			displayUsername: true,
			width: null,
			setupGui: false,
			loggingIn: false,
			feedbackSubject: '[UMC-Feedback] Traceback',
			feedbackAddress: 'feedback@univention.de',
			// default value for the session timeout
			// it will be replaced by the ucr variable 'umc/http/session/timeout' onLogin
			sessionTimeout: 300
		},

		status: function(/*String?*/ key, /*Mixed?*/ value) {
			// summary:
			//		Sets/gets status information. With no parameters given,
			//		returns a dict with status information (username, domainname,
			//		hostname, isSetUpGUI, ...).
			//		With one parameter given, returns the value of the specified key.
			//		With two parameters, sets the value of the specified key.
			//		Also contains the properties given
			//		to `umc/app::start()`. The following properties exist:
			//		* username (String): The username of the authenticated user.
			//		* hostname (String): The hostname on which the UMC is running.
			//		* domainname (String): The domainname on which the UMC is running.
			//		* overview (Boolean): Specifies whether or not the overview is visible.
			//		* displayUsername (Boolean): Specifies whether the username is displayed or not.
			//		* width (Integer): Forces a width for the frontend.
			// key: String?
			//		If given, only the value for the specified property is returned.

			if (undefined === key) {
				// return the whole dictionary
				return this._status;
			}
			if (typeof key == "string") {
				if (undefined === value) {
					// return the specified key
					return this._status[key];
				}
				// set the value
				this._status[key] = value;
			}
			return undefined;
		},

		closeSession: function() {
			// summary:
			//		Reset the session cookie in order to close the session from the client side.
			cookie('UMCSessionId', null, {
				expires: -1,
				path: '/'
			});
		},

		holdSession: function(/*String?*/ id) {
			// summary:
			//		Set the expiration time of the current session cookie in to 24 hours.
			// id: String
			//		If specified, the session ID will be set to this value, otherwise the
			//		ID will be read from the cookie automatically.
			var date = new Date((new Date()).getTime() + 1000 * 60 * 60 * 24);
			cookie('UMCSessionId', id || cookie('UMCSessionId'), {
				expires: date.toUTCString(),
				path: '/'
			});
		},

		// update the cookie data
		_dateRenewIESession : null,

		_markRenewIESession : function() {
			// summary:
			//		Mark that the session will be renewed at the next _checkSessionTimer
			// 		tick. This avoids too many cookie updates at once.
			if(has('ie') !== undefined) {
				this._dateRenewIESession = new Date();
			}
		},

		_renewIESession : function(/*Date?*/_date) {
			// summary:
			//		Reset the Internet Explorer Session. Internet Explorer can not handle max-age cookies.
			//		This is required for automatically show the login dialogue when the session is expired.
			if(has('ie') !== undefined) {
				var date = new Date((_date || new Date()).getTime() + 1000 * this.status('sessionTimeout'));
				cookie('UMCSessionId', cookie('UMCSessionId'), {
					expires: date.toUTCString(),
					path: '/'
				});
			}
		},

		_checkSessionTimer: null,

		checkSession: function(enable) {
			// summary:
			//		Create a background process that checks each second the validity of the session
			//		cookie. As soon as the session is invalid, the login screen will be shown.
			if (enable === false) {
				// stop session checking
				if (this._checkSessionTimer && this._checkSessionTimer.isRunning) {
					this._checkSessionTimer.stop();
				}
				return;
			}

			if (!this._checkSessionTimer) {
				// create a new timer instance
				this._checkSessionTimer = new timing.Timer(1000);
				this._checkSessionTimer.onTick = lang.hitch(this, function() {
					// update cookie for IE if necessary
					if (this._dateRenewIESession) {
						this._renewIESession(this._dateRenewIESession);
						this._dateRenewIESession = null;
					}

					// check whether cookie is still valid
					if (typeof cookie('UMCSessionId') != 'string') {
						this._checkSessionTimer.stop();
						if (tools.status('loggingIn')) {
							// login dialog is already running
							return;
						}

						// try to login
						dialog.login().then(lang.hitch(this, function() {
							if (!this._checkSessionTimer.isRunning) {
								this._checkSessionTimer.start();
							}
						}));
					}
				});
			}

			// start session checking
			if (!this._checkSessionTimer.isRunning) {
				this._checkSessionTimer.start();
			}
		},

		_reloadDialog: null,
		checkReloadRequired: function() {
			if (!this._reloadDialog) {
				// The URL does not exists, so the symlink is deleted
				this._reloadDialog = new ConfirmDialog({
					title: _("UMC reload required"),
					message: _("A reload of the Univention Management Console is required to use new modules.<br>Currently opened modules may not work properly.<br>Do you want to reload the page?"),
					options: [{
						label: _('Cancel'),
						callback: lang.hitch(this, function() {
							this._reloadDialog.hide();
						}),
						'default': true
					}, {
						label: _('Reload'),
						callback: function() {
							window.location.reload();
						}
					}]
				});
			}
			if (!this._reloadDialog.open) {
				// check if UMC needs a browser reload and prompt the user to reload
				return basexhr("HEAD", {url: require.toUrl("umc/")}).then(undefined, lang.hitch(this, function(e) {
					if (e.response.status === 404) {
						this._reloadDialog.show();
					}
				}));
			}
		},

		// handler class for long polling scenario
		_PollingHandler: function(url, content, finishedDeferred, opts) {
			// save the current session ID locally, as the cookie might expire when
			// the time and timezone settings are updated
			var _oldSessionID = cookie('UMCSessionId');

			return {
				finishedDeferred: finishedDeferred,

				// url to which
				url: url,

				// JSON data that is being sent
				content: content,

				// in seconds, timeout that will be passed over to the XHR post command
				xhrTimeout: lang.getObject('xhrTimeout', false, opts) || 300,

				// in seconds, will be multiplied with the number of retries
				timeoutRetry: lang.getObject('timeoutRetry', false, opts) || 2,

				// in seconds, maximal time interval to wait between reestablishing a connection
				maxTimeoutRetry: lang.getObject('maxTimeoutRetry', false, opts) || 30,

				// in seconds, specifies the time interval in which a request is considered
				// to have failed
				failureInterval: lang.getObject('failureInterval', false, opts) || 10,

				// number of seconds after which an information ist displayed to the user
				// in case the connection could not be established; if negative, no message
				// will be shown.
				messageInterval: lang.getObject('messageInterval', false, opts) || 120,

				// message that is displayed to the user in case the
				message: lang.getObject('message', false, opts) || _('So far, the connection to the server could not be established after {time} seconds. This can be a normal behavior. In any case, the process will continue to establish the connection.'),

				// set to true, the _PollingHandler will not try a login
				noLogin: false,

				_startTime: (new Date()).getTime(),

				_lastRequestTime: 0,

				_firstErrorTime: 0,

				_nErrors: 0,

				// information dialog to display to the user
				_dialog: new Dialog({
					title: _('Information'),
					style: 'max-width: 400px'
				}),

				sendRequest: function() {
					// switch off the automatic check for session timeout...
					// the proble here is as follows, we do not receive a response,
					// therefore the cookie is not updated (which is checked for the
					// session timeout), however, the server will renew the session
					// with each valid request that it receives
					var currentSessionID = cookie('UMCSessionId');
					if (!currentSessionID || 'undefined' == currentSessionID) {
						// restore last valid session ID
						currentSessionID = _oldSessionID;
					}
					_oldSessionID = currentSessionID;
					tools.holdSession(currentSessionID);

					// send AJAX command
					this._lastRequestTime = (new Date()).getTime();
					xhr.post(this.url, {
						data: this.content,
						preventCache: true,
						handleAs: 'json',
						headers: {
							'Content-Type': 'application/json'
						},
						timeout: 1000 * this.xhrTimeout
					}).then(lang.hitch(this, function(data) {
						// request finished
						tools._markRenewIESession();
						this._dialog.hide();
						this._dialog.destroyRecursive();
						this.finishedDeferred.resolve(data);
					}), lang.hitch(this, function(error) {
						var result = tools.parseError(error);

						if (!this.noLogin) {
							// handle login cases
							if (401 == result.status) {
								// command was rejected, user is not authorized... continue to poll after successful login
								dialog.login().then(lang.hitch(this, 'sendRequest'));
								return;
							}
							if (411 == result.status) {
								// login failed... continue to poll after successful login
								dialog.login().then(lang.hitch(this, 'sendRequest'));
								dialog.notify(tools._statusMessages[result.status]);
								return;
							}
						}

						// error case
						var elapsedTime = ((new Date()).getTime() - this._lastRequestTime) / 1000.0;
						if (elapsedTime < this.failureInterval) {
							// the server could not been reached within a short time interval
							// -> that is an error
							++this._nErrors;
							if (this._nErrors == 1) {
								// log the error time
								this._firstErrorTime = (new Date()).getTime();
							}
							var elapsedErrorTime = ((new Date()).getTime() - this._firstErrorTime) / 1000.0;
							if (this.messageInterval > 0 && elapsedErrorTime > this.messageInterval && !this._dialog.get('open')) {
								// show message to user
								this._dialog.set('content', lang.replace(this.message, { time: Math.round(elapsedErrorTime) }));
								this._dialog.show();
							}
						}
						else {
							// probably the request got a timeout
							this._nErrors = 0;
							this._firstErrorTime = 0;
						}

						// try again
						setTimeout(lang.hitch(this, 'sendRequest'), 1000 * Math.min(this.timeoutRetry * this._nErrors, this.maxTimeoutRetry));
					}));
				}
			};
		},

		umcpCommand: function(
			/*String*/ commandStr,
			/*Object?*/ dataObj,
			/*Boolean?*/ handleErrors,
			/*String?*/ flavor,
			/*Object?*/ longPollingOptions) {

			// summary:
			//		Encapsulates an AJAX call for a given UMCP command.
			// returns:
			//		A deferred object.

			// when logging in, ignore all except the AUTH command
			if (tools.status('loggingIn') && !(/^auth$/i).test(commandStr)) {
				console.log(_('WARNING: Ignoring command "%s" since user is logging in', commandStr));
				var deferred = new Deferred();
				deferred.reject();
				return deferred;
			}

			// set default values for parameters
			dataObj = dataObj || {};
			handleErrors = undefined === handleErrors || handleErrors;
			// build the URL for the UMCP command
			var url = '/umcp/command/' + commandStr;
			if ((/^(get\/|set$|auth)/i).test(commandStr)) {
				// special case for 'get' and 'auth' commands .. here we do not need to add 'command'
				url = '/umcp/' + commandStr;
			}

			// build message body
			var _body = {
				 options: dataObj
			};
			if (typeof flavor == "string") {
				_body.flavor = flavor;
			}
			tools.removeRecursive(_body, function(key) {
				// hidden properties or un-jsonable values
				return key.substr(0, 18) == '_univention_cache_';
			});
			var body = json.stringify(_body);

			if (longPollingOptions) {
				// long polling AJAX call

				// new handler
				var finishedDeferred = new Deferred();
				var handler = new this._PollingHandler(url, body, finishedDeferred, longPollingOptions);
				handler.sendRequest();

				return finishedDeferred; // Deferred
			}
			else {
				// normal AJAX call
				var call = xhr.post(url, {
					data: body,
					handleAs: 'json',
					headers: {
						'Content-Type': 'application/json'
					}
				});

				call = call.then(function(data) {
					tools._markRenewIESession();
					return data;
				});

				// handle XHR errors unless not specified otherwise
				if (handleErrors) {
					call = call.then(function(data) {
						// do not modify the data
						if ( data && data.message ) {
							if ( parseInt(data.status, 10) == 200 ) {
								dialog.notify( data.message );
							} else {
								dialog.alert( data.message );
							}
						}

						return data; // Object
					}, function(error) {
						// handle errors
						tools.handleErrorStatus(error.response, handleErrors);
						// propagate the error
						throw error;
					});
				}

				// return the Deferred object
				return call; // Deferred
			}
		},

		// _statusMessages:
		//		A dictionary that translates a status to an error message

		// Status( 'SUCCESS'						   , 200, ( 'OK, operation successful' ) ),
		// Status( 'SUCCESS_MESSAGE'				   , 204, ( 'OK, containing report message' ) ),
		// Status( 'SUCCESS_PARTIAL'				   , 206, ( 'OK, partial response' ) ),
		// Status( 'SUCCESS_SHUTDOWN'				  , 250, ( 'OK, operation successful ask for shutdown of connection' ) ),
		//
		// Status( 'CLIENT_ERR_NONFATAL'			   , 301, ( 'A non-fatal error has occured processing may continue' ) ),
		//
		// Status( 'BAD_REQUEST'					   , 400, ( 'Bad request' ) ),
		// Status( 'BAD_REQUEST_UNAUTH'				, 401, ( 'Unauthorized' ) ),
		// Status( 'BAD_REQUEST_FORBIDDEN'			 , 403, ( 'Forbidden' ) ),
		// Status( 'BAD_REQUEST_NOT_FOUND'			 , 404, ( 'Not found' ) ),
		// Status( 'BAD_REQUEST_NOT_ALLOWED'		   , 405, ( 'Command not allowed' ) ),
		// Status( 'BAD_REQUEST_INVALID_ARGS'		  , 406, ( 'Invalid command arguments' ) ),
		// Status( 'BAD_REQUEST_INVALID_OPTS'		  , 407, ( 'Invalid or missing command options' ) ),
		// Status( 'BAD_REQUEST_AUTH_FAILED'		   , 411, ( 'The authentication has failed' ) ),
		// Status( 'BAD_REQUEST_ACCOUNT_EXPIRED'	   , 412, ( 'The account is expired and can not be used anymore' ) ),
		// Status( 'BAD_REQUEST_ACCOUNT_DISABLED'	  , 413, ( 'The account as been disabled' ) ),
		// Status( 'BAD_REQUEST_UNAVAILABLE_LOCALE'	, 414, ( 'Specified locale is not available' ) ),
		//
		// Status( 'SERVER_ERR'						, 500, ( 'Internal error' ) ),
		// Status( 'SERVER_ERR_MODULE_DIED'			, 510, ( 'Module process died unexpectedly' ) ),
		// Status( 'SERVER_ERR_MODULE_FAILED'		  , 511, ( 'Connection to module process failed' ) ),
		// Status( 'SERVER_ERR_CERT_NOT_TRUSTWORTHY'   , 512, ( 'SSL server certificate is not trustworthy' ) ),
		//
		// Status( 'UMCP_ERR_UNPARSABLE_HEADER'		, 551, ( 'Unparsable message header' ) ),
		// Status( 'UMCP_ERR_UNKNOWN_COMMAND'		  , 552, ( 'Unknown command' ) ),
		// Status( 'UMCP_ERR_INVALID_NUM_ARGS'		 , 553, ( 'Invalid number of arguments' ) ),
		// Status( 'UMCP_ERR_UNPARSABLE_BODY'		  , 554, ( 'Unparsable message body' ) ),
		//
		// Status( 'MODULE_ERR'						, 600, ( 'Error occuried during command processing' ) ),
		// Status( 'MODULE_ERR_COMMAND_FAILED'		 , 601, ( 'The execution of a command caused an fatal error' ) )

		_statusMessages: {
			400: _( 'Could not fulfill the request.' ),
			401: _( 'Your session has expired, please login again.' ), // error occurrs only when user is not authenticated and a request is sent
			403: _( 'You are not authorized to perform this action.' ),

			404: _( 'Webfrontend error: The specified request is unknown.' ),
			406: _( 'Webfrontend error: The specified UMCP command arguments of the request are invalid.' ),
			407: _( 'Webfrontend error: The specified arguments for the UMCP module method are invalid or missing.'),
			409: _( 'Webfrontend error: The specified arguments for the UMCP module method are invalid or missing.'), // hack: umcp defined a validation error as 407, but this is not a good http error code

			411: _( 'Authentication failed, please login again.' ),
			412: _( 'The account is expired and can not be used anymore.' ),
			413: _( 'The account as been disabled.' ),
			414: _( 'Specified locale is not available.' ),

			500: _( 'Internal server error.' ),
			503: _( 'Internal server error: The service is temporarily not available.' ),
			510: _( 'Internal server error: The module process died unexpectedly.' ),
			511: _( 'Internal server error: Could not connect to the module process.' ),
			512: _( 'Internal server error: The SSL server certificate is not trustworthy. Please check your SSL configurations.' ),

			551: _( 'Internal UMC protocol error: The UMCP message header could not be parsed.' ),
			554: _( 'Internal UMC protocol error: The UMCP message body could not be parsed.' ),

			590: _( 'Internal module error: An error occured during command processing.' ),
			591: _( 'Could not process the request.' )
		},

		parseError: function(error) {
			var status = error.status !== undefined ? error.status : 500;
			var message = this._statusMessages[status] || this._statusMessages[500];
			var result = null;

			var r = /<title>(.*)<\/title>/;

			if (error.response) {
				try {
					status = error.response.xhr ? error.response.xhr.status : (error.response.status !== undefined ? error.response.status : status ); // status can be 0
				} catch (err) {
					// workaround for Firefox error (Bug #29703)
					status = 0;
				}
				if (error.response.data) {
					// the response contained a valid JSON object, which contents is already html escaped
					status = error.response.data.status && parseInt(error.response.data.status, 10) || status;
					message = error.response.data.message || '';
					result = error.response.data.result || null;
				} else {
					// no JSON was returned, probably proxy error
					message = r.test(error.response.text) ? entities.encode(r.exec(error.response.text)[1]) : (this._statusMessages[status] || this._statusMessages[500]);
				}
			} else if (error.data) {
				if (error.data.xhr) {
					status = error.data.xhr.status;
				} else {
					status = error.data.status !== undefined ? error.data.status : status;
				}
				message = error.data.message || '';
				result = error.data.result || null;
			} else if(error.text) {
				message = r.test(error.text) ? r.exec(error.text)[1] : error.text;
			}

			return {
				status: parseInt(status, 10),
				message: String(message).replace(/\n/g, '<br>'),
				result: result
			};
		},

		handleErrorStatus: function(error, handleErrors) {
			// parse the error
			var info = this.parseError(error);
			var status = info.status;
			var message = info.message;
			var result = info.result;

			// handle the different status codes
			if (undefined !== status && status in this._statusMessages) {
				if (411 == status) {
					// authentification failed, show a notification
					dialog.login();
					var logindialog = query('.umc_LoginMessage');
					logindialog[0].innerHTML = this._statusMessages[status];
					logindialog.style('display', 'block');
				} else if(401 == status) {
					// session has expired
					dialog.login();
					dialog.notify(this._statusMessages[status]);
				} else if (409 == status && handleErrors && handleErrors.onValidationError) {
					// validation error
					handleErrors.onValidationError(message, result);
				}
				/*else if (591 == status) {
					// the command could not be executed, e.g., since the user data was not correct
					// this error deserves a special treatment as it is not critical, but rather a
					// a user error
					dialog.alert('<p>' + this._statusMessages[status] + (message ? ': ' + message : '.') + '</p>');
				}*/
				// handle Tracebacks; on InternalServerErrors(500) they don't contain the word 'Traceback'
				else if(message.match(/Traceback.*most recent call.*File.*line/) || (message.match(/File.*line.*in/) && status >= 500)) {

					var feedbackLink = lang.replace("{0}\n\n1) {1}\n2) {2}\n3) {3}\n\n----------\n\n{4}\n\n----------\n\nunivention-management-console-frontend {5}", [
						_('Please take a second to provide the following information:'),
						_('steps to reproduce the failure'),
						_('expected result'),
						_('actual result'),
						message.replace(/<br *\/?>/g, "\n"),
						tools.status('version')
					]);

					feedbackLink = lang.replace('<a href="mailto:{email}?body={body}&amp;subject={subject}">{title}</a>', {
						email: encodeURIComponent(this.status('feedbackAddress')),
						body: encodeURIComponent(feedbackLink),
						subject: encodeURIComponent(this.status('feedbackSubject')),
						title: _('Send feedback mail')
					});

					var content = '<pre>' + message + '</pre><br>' + feedbackLink;
					var hideLink = '<a>' + _('Hide server error message') + '</a>';
					var showLink = '<a>' + _('Show server error message') + '</a>';

					var titlePane = new TitlePane({
						title: showLink,
						content: content,
						'class': 'umcTracebackPane',
						open: false,
						onHide: function() { titlePane.set('title', showLink); },
						onShow: function() { titlePane.set('title', hideLink); }
					});

					var container = new ContainerWidget({});
					container.addChild(new Text({
						content: '<p>' + this._statusMessages[status] + '</p>'
					}));
					container.addChild(titlePane);

					// center the alert dialog when folding the title pane
					titlePane._wipeIn.on('End', function() { dialog.centerAlertDialog(); } );
					titlePane._wipeOut.on('End', function() { dialog.centerAlertDialog(); } );

					dialog.alert( container );
				}
				else {
					// all other cases
					dialog.alert('<p>' + this._statusMessages[status] + '</p>' + (message ? '<p>' + _('Server error message:') + '</p><p class="umcServerErrorMessage">' + message + '</p>' : ''));
				}
			}
			else if (undefined !== status) {
				// unknown status code .. should not happen
				dialog.alert(_('An unknown error with status code %s occurred while connecting to the server, please try again later.', status));
			}
			else {
				// probably server timeout, could also be a different error
				dialog.alert(_('An error occurred while connecting to the server, please try again later.'));
			}
		},

		forIn: function(/*Object*/ obj, /*Function*/ callback, /*Object?*/ scope, /*Boolean?*/ inheritedProperties) {
			// summary:
			//		Iterate over all elements of an object.
			// description:
			//		Iterate over all elements of an object checking with hasOwnProperty()
			//		whether the element belongs directly to the object.
			//		Optionally, a scope can be defined.
			//		The callback function will be called with the parameters
			//		callback(/*String*/ key, /*mixed*/ value, /*Object*/ obj).
			// 		Returning false from within the callback function will break the loop
			//
			//		This method is similar to dojox/lang/functional/forIn where no hasOwnProperty()
			//		check is carried out.

			scope = scope || _window.global;
			for (var i in obj) {
				if (obj.hasOwnProperty(i) || inheritedProperties) {
					if ( false === callback.call(scope, i, obj[i], obj ) ) {
						break;
					}
				}
			}
		},

		mapWalk: function(/*Array*/ anArray, /*Function*/ callback, /*Object?*/ scope) {
			// summary:
			//		Equivalent to array.map(), however this function is intended to be used
			//		with multi-dimensional arrays.

			// make sure we have an array
			if (!(anArray instanceof Array)) {
				return callback.call(scope, anArray);
			}

			// clone array and walk through it
			scope = scope || _window.global;
			var res = lang.clone(anArray);
			var stack = [ res ];
			while (stack.length) {
				// new array, go through its elements
				var iarray = stack.pop();
				array.forEach(iarray, function(iobj, i) {
					if (iobj instanceof Array) {
						// put arrays on the stack
						stack.push(iobj);
					}
					else {
						// map object
						iarray[i] = callback.call(scope, iobj);
					}
				});
			}

			// return the final array
			return res;
		},

		assert: function(/* boolean */ booleanValue, /* string? */ message){
			// summary:
			// 		Throws an exception if the assertion fails.
			// description:
			// 		If the asserted condition is true, this method does nothing. If the
			// 		condition is false, we throw an error with a error message.
			// booleanValue:
			//		Must be true for the assertion to succeed.
			// message:
			//		A string describing the assertion.

			// throws: Throws an Error if 'booleanValue' is false.
			if(!booleanValue){
				var errorMessage = _('An assert statement failed');
				if(message){
					errorMessage += ':\n' + message;
				}

				// throw error
				var e = new Error(errorMessage);
				throw e;
			}
		},


		cmpObjects: function(/*mixed...*/) {
			// summary:
			//		Returns a comparison functor for Array.sort() in order to sort arrays of
			//		objects/dictionaries.
			// description:
			//		The function arguments specify the sorting order. Each function argument
			//		can either be a string (specifying the object attribute to compare) or an
			//		object with 'attribute' specifying the attribute to compare. Additionally,
			//		the object may specify the attributes 'descending' (boolean), 'ignoreCase'
			//		(boolean).
			//		In order to be useful for grids and sort options, the arguments may also
			//		be one single array.
			// example:
			//	|	var list = [ { id: '0', name: 'Bob' }, { id: '1', name: 'alice' } ];
			//	|	var cmp = tools.cmpObjects({
			//	|		attribute: 'name',
			//	|		descending: true,
			//	|		ignoreCase: true
			//	|	});
			//	|	list.sort(cmp);
			// example:
			//	|	var list = [ { id: '0', val: 100, val2: 11 }, { id: '1', val: 42, val2: 33 } ];
			//	|	var cmp = tools.cmpObjects('val', {
			//	|		attribute: 'val2',
			//	|		descending: true
			//	|	});
			//	|	list.sort(cmp);
			//	|	var cmp2 = tools.cmpObjects('val', 'val2');
			//	|	list.sort(cmp2);

			// in case we got a single array as argument,
			var args = arguments;
			if (1 == arguments.length && arguments[0] instanceof Array) {
				args = arguments[0];
			}

			// prepare unified ordering property list
			var order = [];
			for (var i = 0; i < args.length; ++i) {
				// default values
				var o = {
					attr: '',
					desc: 1,
					ignCase: true
				};

				// entry for ordering can by a String or an Object
				if (typeof args[i] == "string") {
					o.attr = args[i];
				}
				else if (typeof args[i] == "object" && 'attribute' in args[i]) {
					o.attr = args[i].attribute;
					o.desc = (args[i].descending ? -1 : 1);
					o.ignCase = undefined === args[i].ignoreCase ? true : args[i].ignoreCase;
				}
				else {
					// error case
					tools.assert(false, 'Wrong parameter for tools.cmpObjects(): ' + json.stringify(args));
				}

				// add order entry to list
				order.push(o);
			}

			// return the comparison function
			return function(_a, _b) {
				for (var i = 0; i < order.length; ++i) {
					var o = order[i];

					// make sure the attribute is specified in both objects
					if (!(o.attr in _a) || !(o.attr in _b)) {
						return 0;
					}

					// check for lowercase
					var a = _a[o.attr];
					var b = _b[o.attr];
					if (o.ignCase && a.toLowerCase && b.toLowerCase) {
						a = a.toLowerCase();
						b = b.toLowerCase();
					}

					// check for lower/greater
					if (a < b) {
						return -1 * o.desc;
					}
					if (a > b) {
						return 1 * o.desc;
					}
				}
				return 0;
			};
		},

		isEqual: /* Boolean */ function(/* mixed */a, /* mixed */b) {
			// summary:
			//		recursive compare two objects(?) and return true if they are equal
			if (a === b) {
				return true;
			}
			if(typeof a !== typeof b) { return false; }

			// check whether we have arrays
			if (a instanceof Array && b instanceof Array) {
				if (a.length !== b.length) {
					return false;
				}
				for (var i = 0; i < a.length; ++i) {
					if (!tools.isEqual(a[i], b[i])) {
						return false;
					}
				}
				return true;
			}
			if (typeof a == "object" && typeof b == "object" && !(a === null || b === null)) {
				var allKeys = lang.mixin({}, a, b);
				var result = true;
				tools.forIn(allKeys, function(key) {
						result = result && tools.isEqual(a[key], b[key]);
						return result;
				});
				return result;
			}
			return a === b;
		},

		_existingIconClasses: {},

		getIconClass: function(iconName, size, prefix) {
			// check whether the css rule for the given icon has already been added
			size = size || 16;
			var values = {
				s: size,
				icon: iconName
			};
			var iconClass;
			if (iconName.substr(0, 4) == ('http')) {
				// absolute path. use!
				// iconClass must be modified to the icon file name
				values.url = iconName;
				iconClass = lang.replace('abs{s}-{icon}', {s: size, icon: iconName.replace(/\.png$/, '').replace(/.*\//, '')});
			} else {
				// search in local icons directory
				values.url = require.toUrl('dijit/themes');
				values.url = lang.replace("{url}/umc/icons/{s}x{s}/{icon}.png", values);
				iconClass = lang.replace('icon{s}-{icon}', values);
			}
			if (prefix !== undefined) {
				iconClass = lang.replace('{prefix}-{class}', {
					prefix: prefix,
					'class': iconClass
				});
			}
			if (!(iconClass in this._existingIconClasses)) {
				try {
					// add dynamic style sheet information for the given icon
					var css = lang.replace(
						'background: no-repeat;' +
						'width: {s}px; height: {s}px;' +
						'background-image: url("{url}");',
						values);
					styles.insertCssRule('.' + iconClass, css);

					// remember that we have already added a rule for the icon
					this._existingIconClasses[iconClass] = true;
				}
				catch (error) {
					console.log(lang.replace("ERROR: Could not create CSS information for the icon name '{icon}' of size {s}", values));
				}
			}
			return iconClass;
		},

		getUserPreferences: function() {
			var deferred = new Deferred();
			tools.umcpCommand('get/user/preferences', null, false).then(
				function(data) {
					deferred.resolve(data.preferences);
				},
				function(data) {
					deferred.cancel(data);
				}
			);
			return deferred;
		},

		setUserPreference: function(preferences) {
			return tools.umcpCommand('set', {
				user: {	preferences: preferences }
			}, false);
		},

		removeRecursive: function(obj, func) {
			// summary:
			//	Removes recursively from an Object
			//	walks recursively over Arrays and Objects
			tools.forIn(obj, function(key, value) {
				if (func(key)) {
					delete obj[key];
				} else {
					// [] instanceof Object is true, but we test for Array because of readability
					if (value && typeof value != "function" && (value instanceof Array || value instanceof Object)) {
						tools.removeRecursive(value, func);
					}
				}
			});
		},

		delegateCall: function(/*Object*/ self, /*Arguments*/ args, /*Object*/ that) {
			// summary:
			//		Delegates a method call into the scope of a different object.
			var m = self.getInherited(args);
			m.apply(that, args);
		},

		_userPreferences: null, // internal reference to the user preferences

		// internal array with default values for all preferences
		_defaultPreferences: {
			tooltips: true,
			moduleHelpText: true
			//confirm: true
		},

		preferences: function(/*String|Object?*/ param1, /*AnyType?*/ value) {
			// summary:
			//		Convenience function to set/get user preferences.
			//		All preferences will be store in a cookie (in JSON format).
			// returns:
			//		If no parameter is given, returns dictionary with all preference
			//		entries. If one parameter of type String is given, returns the
			//		preference for the specified key. If one parameter is given which
			//		is an dictionary, will set all key-value pairs as specified by
			//		the dictionary. If two parameters are given and
			//		the first is a String, the function will set preference for the
			//		key (paramater 1) to the value as specified by parameter 2.

			// make sure the user preferences are cached internally
			var cookieStr = '';
			if (!this._userPreferences) {
				// not yet cached .. get all preferences via cookies
				this._userPreferences = lang.clone(this._defaultPreferences);
				cookieStr = cookie('UMCPreferences') || '{}';
				lang.mixin(this._userPreferences, json.parse(cookieStr));
			}

			// no arguments, return full preference object
			if (0 === arguments.length) {
				return this._userPreferences; // Object
			}
			// only one parameter, type: String -> return specified preference
			if (1 == arguments.length && typeof param1 == "string") {
				if (param1 in this._defaultPreferences) {
					return this._userPreferences[param1]; // Boolean|String|Integer
				}
				return undefined;
			}

			// backup the old preferences
			var oldPrefs = lang.clone(this._userPreferences);

			// only one parameter, type: Object -> set all parameters as specified in the object
			if (1 == arguments.length) {
				// only consider keys that are defined in defaultPreferences
				tools.forIn(this._defaultPreferences, lang.hitch(this, function(key) {
					if (key in param1) {
						this._userPreferences[key] = param1[key];
					}
				}));
			}
			// two parameters, type parameter1: String -> set specified user preference
			else if (2 == arguments.length && typeof param1 == "string") {
				// make sure preference is in defaultPreferences
				if (param1 in this._defaultPreferences) {
					this._userPreferences[param1] = value;
				}
			}
			// otherwise throw error due to incorrect parameters
			else {
				tools.assert(false, 'tools.preferences(): Incorrect parameters: ' + arguments);
			}

			// publish changes in user preferences
			tools.forIn(this._userPreferences, function(key, val) {
				if (val != oldPrefs[key]) {
					// entry has changed
					topic.publish('/umc/preferences/' + key, val);
				}
			});

			// set the cookie with all preferences
			cookieStr = json.stringify(this._userPreferences);
			cookie('UMCPreferences', cookieStr, { expires: 100, path: '/' } );
			return; // undefined
		},

		ucr: function(/*String|String[]*/ query) {
			// summary:
			//		Function that fetches with the given query the UCR variables.
			// query: String|String[]
			//		Query string (or array of query strings) that is matched on the UCR variable names.
			// return: Deferred
			//		Returns a Deferred that expects a callback to which is passed
			//		a dict of variable name -> value entries.

			return this.umcpCommand('get/ucr',  query  instanceof Array ? query : [ query ] ).then(function(data) {
				return data.result;
			});
		},

		isFalse: function(/*mixed*/ input) {
			if (typeof input == "string") {
				switch (input.toLowerCase()) {
					case 'no':
					case 'not':
					case 'false':
					case '0':
					case 'disable':
					case 'disabled':
					case 'off':
						return true;
				}
			}
			if (false === input || 0 === input || null === input || undefined === input || '' === input) {
				return true;
			}
			return false;
		},

		isTrue: function(/*mixed*/ input) {
			//('yes', 'true', '1', 'enable', 'enabled', 'on')
			return !this.isFalse(input);
		},

		explodeDn: function(dn, noTypes) {
			// summary:
			//		Splits the parts of an LDAP DN into an array.
			// dn: String
			//		LDAP DN as String.
			// noTypes: Boolean?
			//		If set to true, the type part ('.*=') of each LDAP DN part will be removed.

			var res = [];
			if (typeof dn == "string") {
				res = dn.split(',');
			}
			if (noTypes) {
				res = array.map(res, function(x) {
					return x.slice(x.indexOf('=')+1);
				});
			}
			return res;
		},

		ldapDn2Path: function( dn, base ) {
			var base_list = this.explodeDn( base, true );
			var path = '';

			dn = dn.slice( 0, - ( base.length + 1 ) );
			var dn_list = this.explodeDn( dn, true ).slice( 1 );

			// format base
			path = base_list.reverse().join( '.' ) + ':/';
			if ( dn_list.length ) {
				path += dn_list.reverse().join( '/' );
			}

			return path;
		},

		inheritsFrom: function(/*Object*/ _o, /*String*/ c) {
			// summary:
			//		Returns true in case object _o inherits from class c.
			var bases = lang.getObject('_meta.bases', false, _o.constructor);
			if (!bases) {
				// no dojo object
				return false;
			}

			var matched = false;
			array.forEach(bases, function(ibase) {
				if (ibase.prototype.declaredClass == c) {
					matched = true;
					return false;
				}
			});
			return matched;
		},

		capitalize: function(/*String*/ str) {
			// summary:
			//		Return a string with the first letter in upper case.
			if (typeof str != "string") {
				return str;
			}
			return str.slice(0, 1).toUpperCase() + str.slice(1);
		},

		stringOrArray: function(/*String|String[]*/ input) {
			// summary:
			//		Transforms a string to an array containing the string as element
			//		and if input is an array, the array is not modified. In any other
			//		case, the function returns an empty array.

			if (typeof input == "string") {
				return [ input ];
			}
			if (input instanceof Array) {
				return input;
			}
			return [];
		},

		_regFuncAmdStyle: /^javascript:\s*(\w+(\/\w+)*)(:(\w+))?$/,
		_regFuncDotStyle: /^javascript:\s*(\w+(\.\w+)*)$/,

		stringOrFunction: function(/*String|Function*/ input, /*Function?*/ umcpCommand) {
			// summary:
			//		Transforms a string starting with 'javascript:' to a javascript
			//		function, otherwise to an UMCP command function (if umcpCommand)
			//		is specified, and leaves a function a function.
			//		Anything else will be converted to a dummy function.
			// example:
			//		Dot-notation, calling the function foo.bar():
			// |	stringOrFunction('javascript:foo.bar');
			//		Calling the AMD module foo/bar which is expected to be a function:
			// |	stringOrFunction('javascript:foo/bar');
			//		Calling the function doit() of the AMD module foo/bar:
			// |	stringOrFunction('javascript:foo/bar:doit');

			if (typeof input == "function") {
				return input;
			}
			if (typeof input == "string") {
				var match = this._regFuncDotStyle.exec(input);
				var deferred = null;
				if (match) {
					// javascript function in dot style
					return lang.getObject(match[1]);
				}
				match = this._regFuncAmdStyle.exec(input);
				if (match) {
					// AMD module
					deferred = new Deferred();
					try {
						require([match[1]], function(module) {
							if (match[4]) {
								// get the function of the module
								deferred.resolve(module[match[4]]);
							}
							else{
								// otherwise get the full module
								deferred.resolve(module);
							}
						});
					} catch(error) {
						deferred.reject(error);
					}
					// wrapper function which waits for the loaded AMD module
					return function() {
						var args = arguments;
						return deferred.then(function(func) {
							return func.apply(this, args);
						}, function() {});
					};
				}
				if (umcpCommand) {
					// we have a reference to an ucmpCommand, we can try to execute the string as an
					// UMCP command... return function that is ready to query dynamic values via UMCP
					return function(params) {
						return umcpCommand(input, params).then(function(data) {
							// only return the data array
							return data.result;
						});
					};
				}

				// print error message
				console.log('ERROR: The string could not be evaluated as javascript code. Ignoring error: ' + input);
			}

			// return dummy function
			return function() {};
		}
	});

	return tools;
});




