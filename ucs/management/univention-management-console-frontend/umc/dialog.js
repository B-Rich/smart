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
/*global define require*/

define([
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/on",
	"dojo/Deferred",
	"dojo/dom-class",
	"dojo/dom-style",
	"umc/widgets/LoginDialog",
	"umc/widgets/Toaster",
	"umc/widgets/ConfirmDialog",
	"umc/widgets/Text",
	"umc/widgets/Form",
	"umc/tools",
	"umc/i18n/tools",
	"umc/i18n!umc/app"
], function(lang, array, on, Deferred, domClass, domStyle, LoginDialog, Toaster, ConfirmDialog, Text, Form, tools, i18nTools, _) {
	var dialog = {};
	lang.mixin(dialog, {
		_loginDialog: null, // internal reference to the login dialog

		_loginDeferred: null,

		login: function() {
			// summary:
			//		Show the login screen.
			// returns:
			//		A Deferred object that is called upon successful login.
			//		The callback receives the authorized username as parameter.

			if (this._loginDeferred) {
				// a login attempt is currently running
				return this._loginDeferred;
			}

			// check if a page reload is required
			tools.checkReloadRequired();

			// if username and password are specified via the query string, try to authenticate directly
			this._loginDeferred = null;
			var username = tools.status('username');
			var password = tools.status('password');
			if (username && password && typeof username == "string" && typeof password == "string") {
				// try to authenticate via long polling... i.e., in case of an error try again until it works
				this._loginDeferred = tools.umcpCommand('auth', {
					username: username,
					password: password
				}, false, undefined, {
					message: _('So far the authentification failed. Continuing nevertheless.'),
					noLogin: true
				}).then(function() {
					return username;
				});
			}
			else {
				// reject deferred to force login
				this._loginDeferred = new Deferred();
				this._loginDeferred.reject();
			}

			this._loginDeferred = this._loginDeferred.then(null, lang.hitch(dialog, function() {
				// auto authentication could not be executed or failed...

				if (!this._loginDialog) {
					// create the login dialog for the first time
					this._loginDialog = new LoginDialog({});
					this._loginDialog.startup();
				}

				// show dialog
				this._loginDialog.show();
				tools.status('loggingIn', true);

				// connect to the dialog's onLogin event
				var deferred = new Deferred();
				on.once(this._loginDialog, 'login', function(username) {
					// update loggingIn status
					tools.status('loggingIn', false);

					// submit the username to the deferred callback
					deferred.resolve(username);
				});
				return deferred;
			}));

			// after login, set the locale and make sure that the username is passed
			// over to the next callback
			this._loginDeferred = this._loginDeferred.then(lang.hitch(dialog, function(username) {
				// set the locale
				return tools.umcpCommand('set', {
					locale: i18nTools.defaultLang().replace('-', '_')
				}, false).then(function() {
					// remove the reference to the login deferred object
					dialog._loginDeferred = null;

					// make sure the username is handed over to the next callback
					return username;
				}, function() {
					// error... login again
					return dialog.login();
				});
			}));

			return this._loginDeferred;
		},

		loginOpened: function() {
			// summary:
			//		Returns whether the login dialog has been opened or not

			return this._loginDialog && this._loginDialog.open; // Boolean
		},

		_toaster: null, // internal reference to the toaster

		notify: function(/*String*/ message) {
			// summary:
			//		Show a toaster notification with the given message string.
			// message:
			//		The message that is displayed in the notification.

			// create toaster the first time
			if (!this._toaster) {
				this._toaster = new Toaster({});
			}

			// show the toaster
			this._toaster.setContent(message, 'message');
		},

		_alertDialog: null, // internal reference for the alert dialog

		alert: function(/*String*/ message, /* String? */ title, /* String? */ buttonLabel) {
			// summary:
			//		Popup an alert dialog with the given message string. The users needs to
			//		confirm the dialog by clicking on the 'OK' button.
			// message:
			//		The message that is displayed in the dialog.
			// title:
			//		An optional title for the popup window
			// buttonLabel:
			//		An alternative label for the button

			// create alert dialog the first time
			if (!this._alertDialog) {
				this._alertDialog = new ConfirmDialog({
					title: title || _('Notification'),
					style: 'max-width: 650px;',
					options: [{
						label: buttonLabel || _('Ok'),
						callback: lang.hitch(this, function() {
							// hide dialog upon confirmation by click on 'OK'
							this._alertDialog.hide();
						}),
						'default': true
					}]
				});
			}

			// show the confirmation dialog
			this._alertDialog.set('message', message);
			if (title) {
				// update title
				this._alertDialog.set('title', title);
			}
			//this._alertDialog.startup();
			this._alertDialog.show();
		},
		
		centerAlertDialog: function() {
			this._alertDialog._relativePosition = null;
			this._alertDialog._position();
		},

		confirm: function(/*String|_Widget*/ message, /*Object[]*/ options, /*String?*/ title) {
			// summary:
			//		Popup a confirmation dialog with a given message string and a
			//		list of options to choose from.
			// description:
			//		This function provides a shortcut for ConfirmDialog.
			//		The user needs to confirm the dialog by clicking on one of
			//		multiple defined buttons (=choice). When any of the buttons
			//		is pressed, the dialog is automatically closed.
			//		The function returns a Deferred object. Registered callback
			//		methods are called with the corresponding choice name as parameter.
			// message:
			//		The message that is displayed in the dialog, can also be a _Widget.
			// options:
			//		Array of objects describing the possible choices. Array is passed to
			//		ConfirmDialog as 'options' parameter. The property 'label' needs
			//		to be specified. The properties 'callback', 'name', 'auto', and 'default' are
			//		optional.
			//		The property 'default' renders the button for the default choice in the style
			//		of a submit button.
			//		If one single (!) item is specified with the property 'auto=true' and
			//		confirmations are switched off in the user preferences, the dialog is not shown
			//		and the callback function for this default option is executed directly.
			// title:
			//		Optional title for the dialog.
			//
			// example:
			//		A simple example that uses the 'default' property.
			// |	dialog.confirm(msg, [{
			// |	    label: Delete',
			// |	    callback: function() {
			// |			// do something...
			// |		}
			// |	}, {
			// |	    label: 'Cancel',
			// |	    'default': true
			// |	}]);
			// example:
			//		We may also refer the callback to a method of an object, i.e.:
			// |	var myObj = {
			// |		foo: function(answer) {
			// |			if ('delete' == answer) {
			// |				console.log('Item will be deleted!');
			// |			}
			// |		}
			// |	};
			// |	dialog.confirm('Do you want to delete the item?', [{
			// |	    label: 'Delete item',
			// |		name: 'delete',
			// |	    'default': true,
			// |	    callback: lang.hitch(myObj, 'foo')
			// |	}, {
			// |	    label: 'Cancel',
			// |		name: 'cancel',
			// |	    callback: lang.hitch(myObj, 'foo')
			// |	}]);

			// if the user has switched off confirmations, try to find a default option
			if (tools.preferences('confirm') === false) {
				var cb;
				var response;
				array.forEach(options, function(i, idx) {
					// check for default option
					if (true === i.auto) {
						cb = i.callback;
						response = i.name || idx;
						return false; // break loop
					}
				});
				if (cb && typeof cb == "function") {
					// we found a default item .. call the callback and exit
					cb(response);
					return;
				}
			}

			// create confirmation dialog
			var confirmDialog = new ConfirmDialog({
				title: title || _('Confirmation'),
				message: message,
				options: options
			});
			domStyle.set(confirmDialog.containerNode, 'max-width', '550px');

			// connect to 'confirm' event to close the dialog in any case
			var deferred = new Deferred();
			confirmDialog.on('confirm', function(response) {
				confirmDialog.close();
				deferred.resolve(response);
			});

			// show the confirmation dialog
			confirmDialog.show();

			return deferred;
		},

		confirmForm: function(/*Object*/options) {
			// summary:
			// 		Popup a confirmation dialog containing a `umc.widgets.Form' build from the given widgets
			// options:
			// 		Form form: if not given a `umc.widgets.Form' with the igiven widgets and layout will be created.
			// 		Object[] widgets: the form widgets
			// 		Object[] layout: the form layout
			// 		String title: the confirmation dialog title (default: 'Confirmation')
			// 		String style: the confirmation dialog css style (default: 'max-width: 550px;')
			// 		Object[] buttons: overwrite the default submit and cancel button
			// 		String submit: the label for the default submit button (default: 'Submit')
			// 		String cancel: the label for the default cancel button (default: 'Cancel')
			// 		"submit"|"cancel" defaultAction: which default button should be the default? (default: 'submit')

			// create form
			var form = options.form || new Form({
				widgets: options.widgets,
				layout: options.layout
			});

			// define buttons
			var buttons = options.buttons || [{
				name: 'cancel',
				'default': options.defaultAction == 'cancel',
				label: options.close || _('Cancel')
			}, {
				name: 'submit',
				'default': options.defaultAction != 'cancel',
				label: options.submit || _('Submit')
			}];

			// create confirmation dialog
			var confirmDialog = new ConfirmDialog({
				title: options.title || _('Confirmation'),
				style: options.style || 'max-width: 550px;',
				message: form,
				options: buttons
			});

			// check if the submit button is the default action
			if (array.some(buttons, function(button) { return (button.name === 'submit' && button['default']); })) {
				// confirm the dialog if form was submitet
				form.on('submit', function() {
					confirmDialog.onConfirm('submit');
				});
			}

			var deferred = new Deferred();
			confirmDialog.on('confirm', function(response) {
				if ('submit' === response) {
					if (form.validate()) {
						deferred.resolve(form.get('value'));
						confirmDialog.close();
					}
				} else {
					deferred.cancel({
						button: response,
						values: form.get('value')
					});
					confirmDialog.close();
				}
			});
			// user clicked the x on the top right
			confirmDialog.on('hide', function() {
				if (!deferred.isFulfilled()) {
					deferred.cancel({
						button: null,
						values: form.get('value')
					});
				}
			});

			// show the confirmation dialog
			confirmDialog.show();

			return deferred;
		},

		templateDialog: function( /*String*/ templateModule, /*String*/ templateFile, /*String*/ keys, /* String? */ title, /* String? */ buttonLabel ) {
			// summary:
			//		Popup an alert dialog with a text message based on the given template file. The users needs to
			//		confirm the dialog by clicking on the 'OK' button.
			// templateModule:
			//		The module name where to find the template
			// templateFile:
			//		The template file to use
			// keys:
			//		An object with values that should be replaced in the template (using lang.replace)
			// title:
			//		An optional title for the popup window
			// buttonLabel:
			//		An alternative label for the button
			require([lang.replace('dojo/text!{0}/{1}', [templateModule, templateFile])], function(message) {
				message = lang.replace( message, keys );
				var widget = new Text( {  content : message } );
				domClass.add( widget.domNode, 'umcPopup' );
				dialog.alert( widget, title || 'UMC', buttonLabel );
			});
		}
	});
	return dialog;
});

