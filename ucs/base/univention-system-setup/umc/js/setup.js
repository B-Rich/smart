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
/*global define require window setTimeout*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/promise/all",
	"dojo/topic",
	"dojo/when",
	"dojo/json",
	"dojo/Deferred",
	"dijit/Dialog",
	"dojox/timing/_base",
	"umc/tools",
	"umc/dialog",
	"umc/widgets/Text",
	"umc/widgets/Form",
	"umc/widgets/Module",
	"umc/widgets/TabContainer",
	"umc/widgets/ProgressBar",
	"umc/modules/lib/server",
	"umc/i18n!umc/modules/setup",
// Pages:
	"umc/modules/setup/LanguagePage",
	"umc/modules/setup/BasisPage",
	"umc/modules/setup/NetworkPage",
	"umc/modules/setup/CertificatePage",
	"umc/modules/setup/SoftwarePage",
	"umc/modules/setup/SystemRolePage",
	"umc/modules/setup/HelpPage"
], function(declare, lang, array, all, topic, when, json, Deferred, DijitDialog, timing,
	tools, dialog, Text, Form, Module, TabContainer, ProgressBar, libServer, _) {

	var CancelDialogException = declare("umc.modules.setup.CancelDialogException", null, {
		// empty class that indicates that the user canceled a dialog
	});

	return declare("umc.modules.setup", [ Module ], {

		// pages: String[]
		//		List of all setup-pages that are visible.
		pages: [ 'LanguagePage', 'BasisPage', 'NetworkPage', 'CertificatePage', 'SoftwarePage' ],

		// 100% opacity during rendering the module
		//standbyOpacity: 1,

		_pages: null,

		_orgValues: null,

		_currentPage: -1,

		_progressBar: null,

		// internal dict to save error messages while polling
		_saveErrors: null,

		// a timer used it in _cleanup
		// to make sure the session does not expire
		_keepAlive: null,

		// Date when page was last changed
		_timePageChanges: new Date(),

		buildRendering: function() {
			this.inherited(arguments);

			// query the system role
			this.standby(true);

			// make the session not expire
			// before the user can confirm the cleanup dialog
			// started (and stopped) in _cleanup
			this._keepAlive = new timing.Timer(1000 * 30);
			this._keepAlive.onTick = function() {
				// dont do anything important here, just
				// make sure that umc does not forget us
				// dont even handle errors
				tools.umcpCommand('setup/finished', {}, false);
			};

			// load some ucr variables
			var deferred_ucr = tools.ucr(['server/role', 'system/setup/boot/select/role', 'system/setup/boot/pages/whitelist', 'system/setup/boot/pages/blacklist']);
			// load system setup values (e.g. join status)
			var deferred_variables = this.umcpCommand('setup/load');
			// wait for deferred objects to be completed
			var deferredlist = new all([deferred_ucr, deferred_variables]);
			deferredlist.then(lang.hitch(this, function(data) {
				// pass ucr and values to renderPages()
				this.renderPages(data[0], data[1].result);
				this.standbyOpacity = 0.75;  // set back the opacity to 75%
			}));
		},

		renderPages: function(ucr, values) {
			this._progressBar = new ProgressBar();
			this.own(this._progressBar);
			this.standby(true);

			// console.log('joined=' + values.joined);
			// console.log('select_role=' + ucr['system/setup/boot/select/role']);

			var allPages = lang.clone(this.pages);

			var system_role = ucr['server/role'];

			// set wizard mode only on unjoined DC Master
			this.wizard_mode = ( system_role == 'domaincontroller_master') && (! values.joined);

			// we are in locale mode if the user is __systemsetup__
			this.local_mode = tools.status('username') == '__systemsetup__';

			// save current values
			this._orgValues = lang.clone(values);

			// add the SystemRolePage and HelpPage to the list of pages for the wizard mode
			if (this.wizard_mode) {
				// add the SystemRolePage to the list of pages for the wizard mode if the packages have been downloaded
				if (tools.isTrue(ucr['system/setup/boot/select/role'])) {
					allPages.unshift('SystemRolePage');
				}
				allPages.unshift('HelpPage');

				// alter pages by a whitelist and/or blacklist. the pages will be removed without any replacement.
				// empty lists are treated as if they were not defined at all (show all pages). list names should
				// match the names in this.pages and can be separated by a ' '.
				var white_list = ucr['system/setup/boot/pages/whitelist'];
				if (white_list) {
					white_list = white_list.split(' ');
					allPages = array.filter(allPages, function(page) { return array.indexOf(white_list, page) > -1; });
				}
				var black_list = ucr['system/setup/boot/pages/blacklist'];
				if (black_list) {
					black_list = black_list.split(' ');
					allPages = array.filter(allPages, function(page) { return array.indexOf(black_list, page) === -1; });
				}
			}

			if (this.wizard_mode) {
				// wizard mode

				// disallow page changing more than every 500 milliseconds
				this._timerPageChange = new timing.Timer(500);
				this._timerPageChange.onTick = lang.hitch(this, function() { this._timerPageChange.stop(); });

				// create all pages dynamically
				this._pages = [];
				array.forEach(allPages, function(iclass, i) {
					var ipath = 'umc/modules/setup/' + iclass;
					var Class = require(ipath);

					// get the buttons we need
					var buttons = [];
					if (i < allPages.length - 1) {
						buttons.push({
							name: 'submit',
							label: _('Next'),
							callback: lang.hitch(this, function() {
								if (!this._timerPageChange.isRunning) {
									// switch to next visible page
									// precondition: the last page is never invisible!
									var nextpage = i + 1;
									while ((nextpage < allPages.length) && (! this._pages[nextpage].visible)) {
										nextpage += 1;
									}
									this.selectChildIfValid(nextpage);
									this._timerPageChange.start();
								}
							})
						});
					}
					if (i > 0) {
						buttons.push({
							name: 'restore',
							label: _('Back'),
							callback: lang.hitch(this, function() {
								// switch to previous visible page
								// precondition: the first page is never invisible!
								var prevpage = i - 1;
								while ((0 < prevpage) && (! this._pages[prevpage].visible)) {
									prevpage -= 1;
								}
								this.selectChild(this._pages[prevpage]);
							})
						});
					}
					if (i == allPages.length - 1) {
						buttons.push({
							name: 'submit',
							label: _('Apply settings'),
							callback: lang.hitch(this, function() {
								this.save();
							})
						});
					}

					// make a new page
					var ipage = new Class({
						umcpCommand: lang.hitch(this, 'umcpCommand'),
						footerButtons: buttons,
						moduleFlavor: this.moduleFlavor,
						wizard_mode: this.wizard_mode,
						local_mode: this.local_mode
					});
					ipage.on('save', lang.hitch(this, function() {
						if (i < allPages.length - 1) {
							// switch to next visible page
							// precondition: the last page is never invisible!
							var nextpage = i + 1;
							while ((nextpage < allPages.length) && (! this._pages[nextpage].visible)) {
								nextpage += 1;
							}
							this.selectChildIfValid(nextpage);
						} else {
							this.save();
						}
					}));
					this.addChild(ipage);
					this._pages.push(ipage);

					// connect to valuesChanged callback of every page
					ipage.setValues(values);
					ipage.on('valuesChanged', lang.hitch(this, 'updateAllValues'));
				}, this);
				// Now we know which pages were loaded, adjust HelpPage text
				array.forEach(this._pages, lang.hitch(this, function(page) {
					// if page is HelpPage...
					if (page.setHelp !== undefined) {
						page.setHelp(this._pages);
					}
				}));
			}
			else {
				// normal mode... we need a TabContainer
				var tabContainer = new TabContainer({
					nested: true
				});

				// each page has the same buttons for saving/resetting
				var buttons = [ {
						name: 'close',
						label: _( 'Close' ),
						align: 'left',
						callback: lang.hitch( this, function() {
							dialog.confirm( _( 'Should the UMC module be closed? All unsaved modification will be lost.' ), [ {
								label: _( 'Close' ),
								callback: lang.hitch( this, function() {
									topic.publish('/umc/tabs/close', this );
								} )
							}, {
								label: _( 'Cancel' ),
								'default': true
							} ] );
						} )
				}, {
					name: 'submit',
					label: _( 'Apply changes' ),
					callback: lang.hitch(this, function() {
						this.save();
					})
				}, {
					name: 'restore',
					label: _('Reset'),
					callback: lang.hitch(this, function() {
						this.load();
					})
				}];

				// create all pages dynamically
				this._pages = [];
				array.forEach(allPages, function(iclass) {
					// create new page
					var ipath = 'umc/modules/setup/' + iclass;
					var Class = require(ipath);
					var ipage = new Class({
						umcpCommand: lang.hitch(this, 'umcpCommand'),
						footerButtons: buttons,
						moduleFlavor: this.moduleFlavor,
						wizard_mode: this.wizard_mode,
						local_mode: this.local_mode,
						onSave: lang.hitch(this, function() {
							this.save();
						})
					});
					tabContainer.addChild(ipage);
					this._pages.push(ipage);

					// connect to valuesChanged callback of every page
					ipage.setValues(values);
					ipage.on('valuesChanged', lang.hitch(this, 'updateAllValues'));

					// hide tab if page is not visible
					this.own(ipage.watch('visible', function(name, oldval, newval) {
						if ((newval === true) || (newval === undefined)) {
							tabContainer.showChild(ipage);
						} else {
							tabContainer.hideChild(ipage);
						}
					}));
				}, this);

				this.addChild(tabContainer);
			}

			this.startup();
			this.standby(false);
		},

		updateAllValues: function(name, old, values) {
			var vals = lang.clone(this._orgValues);
			lang.mixin(vals, this.getValues());
			array.forEach(this._pages, function(ipage) {
				ipage.setValues(vals);
			}, this);
		},

		setValues: function(values) {
			// update all pages with the given values
			this._orgValues = lang.clone(values);
			array.forEach(this._pages, function(ipage) {
				ipage.setValues(this._orgValues);
			}, this);
		},

		getValues: function() {
			var values = {};
			array.forEach(this._pages, function(ipage) {
				lang.mixin(values, ipage.getValues());
			}, this);
			return values;
		},

		load: function() {
			// get settings from server
			this.standby(true);
			return this.umcpCommand('setup/load').then(lang.hitch(this, function(data) {
				// update setup pages with loaded values
				this.setValues(data.result);
				this.standby(false);
			}), lang.hitch(this, function() {
				this.standby(false);
			}));
		},

		save: function() {
			// helper function 
			var matchesSummary = function(key, summary) {
				var matched = false;
				// iterate over all assigned variables
				array.forEach(summary.variables, function(ikey) {
					// key is a regular expression or a string
					if (typeof ikey == "string" && key == ikey ||
							ikey.test && ikey.test(key)) {
						matched = true;
						return false;
					}
				});
				return matched;
			};

			// confirm dialog to continue with boot process
			var _cleanup = lang.hitch(this, function(msg, hasCancel, loadAfterCancel, cancelLabel, applyLabel) {
				if (cancelLabel === undefined) {
					cancelLabel = _('Cancel');
				}
				if (applyLabel === undefined) {
					applyLabel = _('Continue');
				}
				var choices = [{
					name: 'apply',
					'default': true,
					label: applyLabel
				}];
				if (hasCancel) {
					// show continue and cancel buttons
					choices = [{
						name: 'cancel',
						'default': true,
						label: cancelLabel
					}, {
						name: 'apply',
						label: applyLabel
					}];
				}

				this._keepAlive.start();

				return dialog.confirm(msg, choices, true).then(lang.hitch(this, function(response) {
					if (response == 'cancel') {
						// do not continue
						this._keepAlive.stop();
						if (loadAfterCancel) {
							this.load();
						}
						return;
					}

					// shut down web browser and restart apache and UMC
					// use long polling to make sure the command succeeds (Bug #27632)
					return this.umcpCommand('setup/cleanup', {}, undefined, undefined, {
						// long polling options
						messageInterval: 30,
						xhrTimeout: 40
					}).then(lang.hitch(this, function() {
						// redirect to UMC and set username to Administrator on DC master
						var username = 'Administrator';
						if (this.role == 'basesystem') {
							// use root on basesystem
							username = 'root';
						}
						var target = window.location.href.replace(new RegExp( "/univention-management-console.*", "g" ), '/univention-management-console/?username=' + username);

						// Consider IP changes, replace old ip in url by new ip
						tools.forIn(this._orgValues, function(ikey, ival) {
							// 1. check if value is equal to the current IP
							// 2. check if the key for this value startswith interfaces/
							// 3. check if a new value was set
							if ((ival == window.location.host) && (ikey.indexOf('interfaces/') === 0)  && (values[ikey])) {
								target = target.replace(new RegExp(ival+"/univention-management-console", "g"), values[ikey]+"/univention-management-console");
							}
						});

						// give the restart/services function 10 seconds time to restart the services
						setTimeout(function () {
							window.location.replace(target);
						}, 10000);
					}));
				}));
			});

			// get all entries that have changed and collect a summary of all changes
			var values = {};
			var nchanges = 0;
			var inverseKey2Page = {};  // saves which key belongs to which page
			var summaries = [];
			var umc_url = null;

			array.forEach(this._pages, function(ipage) {
				var pageVals = ipage.getValues();
				var summary = ipage.getSummary();
				summaries = summaries.concat(summary);

				// get altered values from page
				tools.forIn(pageVals, function(ikey, ival) {
					inverseKey2Page[ikey] = ipage;
					var orgVal = this._orgValues[ikey];
					orgVal = undefined === orgVal || null === orgVal ? '' : orgVal;
					var newVal = undefined === ival || null === ival ? '' : ival;
					// some variables (notably locale)
					// were sent as [{id:id, label:label}, ...]
					// but will be returned as [id, ...]
					if (orgVal instanceof Array) {
						var tmpOrgVal = [];
						array.forEach(orgVal, function(iOrgVal) {
							if (iOrgVal.id !== undefined && iOrgVal.label !== undefined) {
								tmpOrgVal.push(iOrgVal.id);
							}
						});
						if (tmpOrgVal.length) {
							orgVal = tmpOrgVal;
						}
					}
					if (json.stringify(orgVal) != json.stringify(newVal)) {
						values[ikey] = newVal;
						++nchanges;

						// check whether a redirect to a new IP address is necessary
						if ( umc_url === null ) {
							if ( ikey == 'interfaces/eth0/address' && newVal ) {
								umc_url = 'https://' + newVal + '/umc/';
							} else if ( ikey == 'interfaces/eth0/ipv6/default/address' && newVal ) {
								umc_url = 'https://[' + newVal + ']/umc/';
							}
						}
					}
				}, this);
			}, this);

			// initiate some local check variables
			var joined = this._orgValues.joined;
			var newValues = this.getValues();
			var role = newValues['server/role'];
			if (!role) {
				role = this._orgValues['server/role'];
			}

			// only submit data to server if there are changes and the system is joined
			if (!nchanges && !this.wizard_mode) {
				dialog.alert(_('No changes have been made.'));
				return;
			}

			// see whether a UMC server, UMC web server, and apache restart is necessary:
			// -> installation/removal of software components
			var umcRestart = 'components' in values;

			// check whether all page widgets are valid
			var allValid = true;
			var validationMessage = '<p>' + _('The following entries could not be validated:') + '</p><ul style="max-height:200px; overflow:auto;">';
			array.forEach(this._pages, function(ipage) {
				if (!ipage._form) {
					return true;
				}
				tools.forIn(ipage._form._widgets, function(ikey, iwidget) {
					if (iwidget.isValid && false === iwidget.isValid()) {
						allValid = false;
						validationMessage += '<li>' + ipage.get('title') + '/' + iwidget.get('label') + '</li>';
					}
				});
			});
			if (!allValid) {
				this.standby(false);
				dialog.alert(validationMessage);
				return;
			}

			// validate the changes
			this.standby(true);
			this.umcpCommand('setup/validate', { values: values }).then(lang.hitch(this, function(data) {
				var allValid = true;
				array.forEach(data.result, function(ivalidation) {
					allValid = allValid && ivalidation.valid;
					if (ivalidation.message) {
						// find the correct description to be displayed
						array.forEach(summaries, function(idesc) {
							if (matchesSummary(ivalidation.key, idesc)) {
								idesc.validationMessages = idesc.validationMessages || [];
								idesc.validationMessages.push(ivalidation.message);
							}
						});

					}
				});

				// construct message for validation
				array.forEach(summaries, function(idesc) {
					//console.log('#', json.stringify(idesc));
					array.forEach(idesc.validationMessages || [], function(imsg) {
						validationMessage += '<li>' + idesc.description + ': ' + imsg + '</li>';
					});
				});

				if (!allValid) {
					// something could not be validated
					this.standby(false);
					dialog.alert(validationMessage);
					return;
				}

				// function to confirm changes
				var _confirmChanges = lang.hitch(this, function() {
					// first see which message needs to be displayed for the confirmation message
					tools.forIn(values, function(ikey) {
						array.forEach(summaries, function(idesc) {
							if (matchesSummary(ikey, idesc)) {
								idesc.showConfirm = true;
							}
						});
					});

					// construct message for confirmation
					var confirmMessage = '<p>' + _('The following changes will be applied to the system:') + '</p><ul style="max-height:200px; overflow:auto;">';
					array.forEach(summaries, function(idesc) {
						if (idesc.showConfirm) {
							confirmMessage += '<li>' + idesc.description + ': ' + idesc.values + '</li>';
						}
					});
					confirmMessage += '</ul><p>' + _('Please confirm to apply these changes to the system. This may take some time.') + '</p>';

					return dialog.confirm(confirmMessage, [{
						name: 'cancel',
						'default': true,
						label: _('Cancel')
					}, {
						name: 'apply',
						label: _('Apply changes')
					}]).then(lang.hitch(this, function(response) {
						if ('apply' != response) {
							// throw new error to indicate that action has been canceled
							throw new CancelDialogException();
						}
						this.standby( false );
					}));
				});

				// function to ask the user for DC account data
				var _password = lang.hitch(this, function() {
					var msg = '<p>' + _('The specified settings will be applied to the system and the system will be joined into the domain. Please enter username and password of a domain administrator account.') + '</p>'; 
					var deferred = new Deferred();
					var _dialog = null;
					var form = new Form({
						widgets: [{
							name: 'text',
							type: Text,
							content: msg
						}, {
							name: 'username',
							type: 'TextBox',
							label: _('Username')
						}, {
							name: 'password',
							type: 'PasswordBox',
							label: _('Password')
						}],
						buttons: [{
							name: 'submit',
							label: _('Join'),
							callback: lang.hitch(this, function() {
								this.standby(false);
								deferred.resolve({
									username: form.getWidget('username').get('value'),
									password: form.getWidget('password').get('value')
								});
								_dialog.hide();
								_dialog.destroyRecursive();
								form.destroyRecursive();
							})
						}, {
							name: 'cancel',
							label: _('Cancel'),
							callback: lang.hitch(this, function() {
								deferred.reject();
								this.standby(false);
								_dialog.hide();
								_dialog.destroyRecursive();
								form.destroyRecursive();
							})
						}],
						layout: [ 'text', 'username', 'password' ]
					});
					_dialog = new DijitDialog({
						title: _('Account data'),
						content: form,
						style: 'max-width: 400px;'
					});
					_dialog.on('Hide', lang.hitch(this, function() {
						if (!deferred.isFulfilled()) {
							// user clicked the close button
							this.standby(false);
							deferred.reject();
						}
					}));
					_dialog.show();
					return deferred;
				});

				// confirmation message for the master
				var _confirmMaster = lang.hitch(this, function() {
					var msg = '<p>' + _('The specified settings will be applied to the system. This may take some time. Please confirm to proceed.') + '</p>';
					return dialog.confirm(msg, [{
						name: 'cancel',
						label: _('Cancel')
					}, {
						name: 'apply',
						'default': true,
						label: _('Apply changes')
					}]).then(lang.hitch(this, function(response) {
						if ('apply' != response) {
							// throw new error to indicate that action has been canceled
							throw new CancelDialogException();
						}
						this.standby( false );
					}));
				});

				// function to save data
				var _save = lang.hitch(this, function(username, password) {
					// make sure that the parameters are not undefined,
					// otherwise an 'Invalid JSON Document' is return by the server
					username = username || null;
					password = password || null;

					var deferred = new Deferred();

					// send save command to server
					this._progressBar.reset(_( 'Initialize the configuration process ...' ));
					this.standby( true, this._progressBar );
					var command = null;
					if (!this.wizard_mode || role == 'basesystem') {
						command = this.umcpCommand('setup/save', {
							values: values
						});
					} else {
						command = this.umcpCommand('setup/join', {
							values: values,
							username: username,
							password: password
						});
					}
					command.then(lang.hitch(this, function() {
						// poll whether script has finished
						this._progressBar.auto(
							'setup/finished',
							{},
							lang.hitch(deferred, 'resolve'),
							lang.replace( _( 'The connection to the server could not be established after {time} seconds. This problem can occur due to a change of the IP address. In this case, please login to Univention Management Console again at the {linkStart}new address{linkEnd}.' ), { 
								time: '{time}',
								linkStart : umc_url ? '<a href="' + umc_url + '">' : '',
								linkEnd : umc_url ? '</a>' : ''
							} ),
							_('Configuration finished'),
							true
						);
					}));

					return deferred;
				});

				// ask user whether UMC server components shall be restarted or not
				var _restart = lang.hitch(this, function() {
					libServer.askRestart(_('The changes have been applied successfully.'));
					this.load(); // sets 'standby(false)'
				});

				// notify user that saving was successful
				var _success = lang.hitch(this, function() {
					dialog.notify(_('The changes have been applied successfully.'));
					this.load(); // sets 'standby(false)'
				});

				// tell user that saving was not successful (has to confirm)
				var _failure = lang.hitch(this, function(errorHtml) {
					var msg = this._embedErrorHTML(_('Not all changes could be applied successfully:'), errorHtml);
					var choices = [{
						name: 'apply',
						'default': true,
						label: _('Ok')
					}];
					return dialog.confirm(msg, choices).then(lang.hitch(this, function(response) {
						this.load(); // sets 'standby(false)'
						return;
					}));
				});
				// show the correct dialogs
				var deferred = null;
				if (!this.wizard_mode) {
					// normal setup scenario, confirm changes and then save
					deferred = _confirmChanges().then(function() {
						return _save();
					});
				}
				else if (role != 'domaincontroller_master') {
					// unjoined system scenario and not master
					// we need a proper DC administrator account
					deferred = _password().then(function(opt) {
						return _save(opt.username, opt.password);
					});
				}
				else {
					// unjoined master
					deferred = _confirmMaster().then(function() {
						return _save();
					});
				}

				if (this.wizard_mode) {
					// kill the browser and restart the UMC services in wizard mode
					deferred = deferred.then(lang.hitch(this, function() {
						var errors = this._progressBar.getErrors();
						var errorHtml = this._buildErrorHtml(errors.errors);
						if (!errorHtml) {
							return _cleanup(_('The configuration was successful. Please confirm to complete the process.'));
						} else if (errors.critical) {
							return _cleanup(this._embedErrorHTML(
								_('The system join was not successful.'),
								errorHtml,
								_('You may return, reconfigure the settings, and retry the join process. You may also continue and end the wizard leaving the system unjoined. The system can be joined later via the UMC module "Domain join".')
								), true, true, _('Reconfigure, retry'), _('Continue unjoined'));
						} else {
							return _cleanup(this._embedErrorHTML(
								_('The system join was successful, however, errors occurred while applying the configuration settings:'),
								errorHtml,
								_('The settings can be changed in the UMC module "Basic settings" after the join process has been completed. Please confirm now to complete the process.')
								));
						}
					}));
				}
				else {
					// show success/error message and eventually restart UMC server components
					deferred = deferred.then(lang.hitch(this, function() {
						var errors = this._progressBar.getErrors();
						var errorHtml = this._buildErrorHtml(errors.errors);
						if (errorHtml) {
							// errors have occurred
							return _failure(errorHtml);
						} else {
							// everything went well :)
							if (umcRestart) {
								return _restart();
							}
							else {
								return _success();
							}
						}
					}));
				}

				// error case, turn off standby animation
				deferred.then(
					function() {},
					lang.hitch(this, function() {
						this.standby(false); 
					})
				);
			}), lang.hitch(this, function() {
				this.standby(false);
			}));
		},

		_buildErrorHtml: function(errors) {
			var errorHtml = '';
			array.forEach(errors, function(error) {
				errorHtml += '<li>' + error + '</li>';
			});
			if (errorHtml) {
				errorHtml = '<ul style="overflow: auto; max-height: 400px;">' + errorHtml + '</ul>';
			}
			return errorHtml;
		},

		_embedErrorHTML: function(first, errorHtml, last) {
			var html = errorHtml;
			if (first) {
				html = first + html;
			}
			if (last) {
				html = html + last;
			}
			return html;
		},

		selectChildIfValid: function(nextpage) {
			var current_page = this._pages[nextpage - 1];
			when(current_page.validate === undefined || current_page.validate(),
				lang.hitch(this, function(value) {
					if (value) {
						var page = this._pages[nextpage];
						this.selectChild(page);
						// focus first widget in page
						// if (page._form) {
						// 	tools.forIn(page._form._widgets, function(iname, iwidget) {
						// 		if (!iwidget.get('disabled')) {
						// 			try {
						// 				iwidget.focus();
						// 			} catch(e) {
						// 			}
						// 			return false;
						// 		}
						// 	});
						// }
					}
				})
			);
		}

	});
});
