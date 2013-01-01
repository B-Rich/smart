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
/*global define*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dijit/ProgressBar",
	"umc/tools",
	"umc/dialog",
	"umc/widgets/ContainerWidget",
	"umc/widgets/Text",
	"umc/i18n!umc/app"
], function(declare, lang, array, ProgressBar, tools, dialog, ContainerWidget, Text, _) {
	return declare("umc.widgets.ProgressBar", ContainerWidget, {
		// summary:
		//		This class provides a widget providing detailed progress information

		i18nClass: 'umc.modules.setup',

		style: 'width: 400px',

		_component: null,
		_message: null,
		_progressBar: null,
		_errors: null,
		_criticalError: null,

		_initialComponent: null,

		buildRendering: function() {
			this.inherited(arguments);

			this._component = new Text({ content : '' , style : 'width: 100%' });
			this.addChild(this._component);
			this._progressBar = new ProgressBar({ style : 'width: 100%' });
			this.addChild(this._progressBar);
			this._message = new Text({ content : '&nbsp;', style : 'width: 100%' });
			this.addChild(this._message);

			this._progressBar.set('value', 0);
			this._progressBar.set('maximum', 100);

			this.reset();
			this.startup();
		},

		reset: function(initialComponent) {
			if (initialComponent) {
				this._initialComponent = initialComponent;
			}
			this._criticalError = false;
			this._errors = [];

			this._component.set('content', this._initialComponent);

			// make sure that at least a not breakable space is printed
			// ... this avoids vertical jumping of widgets
			this._message.set('content', '&nbsp;');

			this._progressBar.set('value', 0);
		},

		setInfo: function(component, message, percentage, errors, critical) {
			if (component) {
				this._component.set('content', component);
			}
			if (percentage) {
				this._progressBar.set('value', percentage);
			}
			if (message || component) {
				this._message.set('content', message || '&nbsp;');
			}
			this._addErrors(errors);
			if (critical) {
				this._criticalError = true;
			}
		},

		_addErrors: function(errors) {
			array.forEach(errors, lang.hitch(this, function(error) {
				if (error) {
					if (array.indexOf(this._errors, error) === -1) {
						this._errors.push(error);
					}
				}
			}));
		},

		auto: function(umcpCommand, umcpOptions, callback, pollErrorMsg, stopComponent, dontHandleErrors) {
			if (pollErrorMsg === undefined) {
				pollErrorMsg = _('Fetching information from the server failed!');
			}
			tools.umcpCommand(umcpCommand,
				umcpOptions, undefined, undefined,
				{
					messageInterval: 30,
					message: pollErrorMsg,
					xhrTimeout: 40
				}
			).then(lang.hitch(this, function(data) {
				var result = data.result;
				if (result) {
					this.setInfo(result.component, result.info, result.steps, result.errors, result.critical);
					if (!result.finished) {
						this.auto(umcpCommand, umcpOptions, callback, pollErrorMsg, stopComponent, dontHandleErrors);
					}
				}
				if (!result || result.finished) {
					this.stop(callback, stopComponent, !dontHandleErrors);
				}
			}));
		},

		stop: function(callback, stopComponent, handleErrors) {
			var errors = this.getErrors().errors;
			if (errors.length && handleErrors) {
				var msg = '';
				if (errors.length == 1) {
					msg = _('An error occurred: ') + errors[0];
				} else {
					msg = lang.replace(_('{number} errors occurred: '), {number : errors.length});
					msg += '<ul><li>' + errors.join('</li><li>') + '</li></ul>';
				}
				dialog.confirm(msg, [{
					label: 'Ok',
					'default': true,
					callback: callback
				}]);
			} else {
				callback();
			}
		},

		getErrors: function() {
			return {'errors' : this._errors, 'critical' : this._criticalError};
		}
	});
});
