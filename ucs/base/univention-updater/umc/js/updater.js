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
/*global define console*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dijit/Dialog",
	"umc/dialog",
	"umc/widgets/ConfirmDialog",
	"umc/widgets/Module",
	"umc/modules/updater/UpdatesPage",
	"umc/modules/updater/ProgressPage",
	"umc/i18n!umc/modules/updater"
], function(declare, lang, array, Dialog, dialog, ConfirmDialog, Module, UpdatesPage, ProgressPage, _) {
	return declare("umc.modules.updater", Module, {

		// some variables related to error handling
		_connection_status:	0, 			// 0 ... successful or not set
										// 1 ... errors received
										// 2 ... currently authenticating
		_busy_dialog: null, 		// a handle to the 'connection lost' dialog while
								// queries return with errors.
		_error_count: 0, 		// how much errors in one row

		buildRendering: function() {

			this.inherited(arguments);

			this._updates = new UpdatesPage({standby: lang.hitch(this, 'standby')});
			this._progress = new ProgressPage({});

			this.addChild(this._updates);
			this.addChild(this._progress);

			// --------------------------------------------------------------------------
			//
			//		Connections that make the UI work (mostly tab switching)
			//

			this._progress.on('stopwatching', lang.hitch(this, function() {
				// Revert to the 'Updates' page if the installer action encountered
				// the 'reboot' affordance.
				this.selectChild(this._updates);
			}));

			// waits for the Progress Page to notify us that a job is running
			this._progress.on('jobstarted', lang.hitch(this, function() {
				this._switch_to_progress_page();
			}));

			// --------------------------------------------------------------------------
			//
			//		Connections that listen for changes and propagate
			//		them to other pages
			//

			// *** NOTE *** the Updates Page also has some mechanisms to refresh itself
			//				on changes that reflect themselves in the sources.list
			//				snippet files. But this refresh is intentionally slow (once
			//				in 5 secs) to avoid resource congestion. The callbacks here
			//				should immediately trigger refresh whenever something was
			//				done at the frontend UI.

			// ---------------------------------------------------------------------------
			//
			//		Listens for 'query error' and 'query success' events on all attached pages
			//		and their children, delivering them to our own (central) error handler
			//

			array.forEach(this.getChildren(), lang.hitch(this, function(child) {
				child.on('queryerror', lang.hitch(this, function(subject, data) {
					this.handleQueryError(subject, data);
				}));

				child.on('querysuccess', lang.hitch(this, function(subject, data) {
					this.handleQuerySuccess(subject, data);
				}));
			}));

			// --------------------------------------------------------------------------
			//
			//		Connections that centralize the work of the installer:
			//		listen for events that should start UniventionUpdater
			//

			// invokes the installer from the 'release update' button (Updates Page)
			this._updates.on('runreleaseupdate', lang.hitch(this, function(release) {
				this._call_installer({
					job:		'release',
					detail:		release,
					confirm:	lang.replace(_("Do you really want to install release updates up to version {release}?"), {release: release})
				});
			}));

			// invokes the installer from the 'component update' button (Updates Page)
			this._updates.on('rundistupgrade', lang.hitch(this, function() {
				this._confirm_distupgrade();
			}));

			// invokes the installer in easy mode
			this._updates.on('runeasyupgrade', lang.hitch(this, function() {
				this._call_installer({
					job:		'easyupgrade',
					confirm:	_("Do you really want to upgrade your system?")
				});
			}));

			// propagate the status information to other pages
			this._updates.on('statusloaded', lang.hitch(this, function(vals) {
				this._progress.updateStatus(vals);
			}));
		},

		// We defer these actions until the UI is readily rendered
		startup: function() {

			this.inherited(arguments);

			this.selectChild(this._updates);

		},

		// Seperate function that can be called the same way as _call_installer:
		// instead of presenting the usual confirm dialog it presents the list
		// of packages for a distupgrade.
		_confirm_distupgrade: function() {

			try
			{
				this.standby(true);
				this.umcpCommand('updater/updates/check').then(lang.hitch(this, function(data) {
					this.standby(false);
					// FIXME Lots of manual styling to achieve resonable look
					var txt = "<div style='overflow:auto;max-height:500px;'><table>\n";
					var upd = data.result.update;
					var ins = data.result.install;
					var rem = data.result.remove;
					if ((! upd.length) && (! ins.length) && (! rem.length))
					{
						this._updates.refreshPage(true);
						return;
					}
					if (rem.length)
					{
						txt += "<tr><td colspan='2' style='padding:.5em;'><b><u>";
						if (rem.length == 1)
						{
							txt += lang.replace(_("1 package to be REMOVED"));
						}
						else
						{
							txt += lang.replace(_("{count} packages to be REMOVED"), {count:rem.length});
						}
						txt += "</u></b></td></tr>";
						array.forEach(rem, function(pkg) {
							txt += "<tr>\n";
							txt += "<td style='padding-left:1em;'>" + pkg[0] + "</td>\n";
							txt += "<td style='padding-left:1em;padding-right:.5em;'>" + pkg[1] + "</td>\n";
							txt += "</tr>\n";
						});
					}
					if (upd.length)
					{
						txt += "<tr><td colspan='2' style='padding:.5em;'><b><u>";
						if (upd.length == 1)
						{
							txt += lang.replace(_("1 package to be updated"));
						}
						else
						{
							txt += lang.replace(_("{count} packages to be updated"), {count:upd.length});
						}
						txt += "</u></b></td></tr>";
						array.forEach(upd, function(pkg) {
							txt += "<tr>\n";
							txt += "<td style='padding-left:1em;'>" + pkg[0] + "</td>\n";
							txt += "<td style='padding-left:1em;padding-right:.5em;'>" + pkg[1] + "</td>\n";
							txt += "</tr>\n";
						});
					}
					if (ins.length)
					{
						txt += "<tr><td colspan='2' style='padding:.5em;'><b><u>";
						if (ins.length == 1)
						{
							txt += lang.replace(_("1 package to be installed"));
						}
						else
						{
							txt += lang.replace(_("{count} packages to be installed"), {count:ins.length});
						}
						txt += "</u></b></td></tr>";
						array.forEach(ins, function(pkg) {
							txt += "<tr>\n";
							txt += "<td style='padding-left:1em;'>" + pkg[0] + "</td>\n";
							txt += "<td style='padding-left:1em;padding-right:.5em;'>" + pkg[1] + "</td>\n";
							txt += "</tr>\n";
						});
					}
					txt += "</table></div>";
					txt += "<p style='padding:1em;'>" + _("Do you really want to perform the update/install/remove of the above packages?") + "</p>\n";
					var dia = new ConfirmDialog({
						title:			_("Start Upgrade?"),
						message:		txt,
						style:			'max-width:650px;',
						options:
						[
							{
								label:		_('Cancel'),
								name:		'cancel'
							},
							{
								label:		_('Install'),
								name:		'start',
								'default':	true
							}
						]
					});

					dia.on('confirm', lang.hitch(this, function(answer) {
						dia.close();
						if (answer == 'start')
						{
							this._call_installer({
								confirm:		false,
								job:			'distupgrade',
								detail:			''
							});
						}
					}));
					dia.show();

					return;
				}),
				lang.hitch(this, function() {
					this.standby(false);
				})
				);
			}
			catch(error)
			{
				console.error("PACKAGE DIALOG: " + error.message);
			}
		},

		// Central entry point into all installer calls. Subject
		// and detail are passed as args to the 'updater/installer/execute' backend.
		//
		// Argument 'confirm' has special meaning:
		//		true ......... ask for confirmation and run the installer only if confirmed,
		//		false ........ run the installer unconditionally.
		//		any string ... the confirmation text to ask.
		_call_installer: function(args) {

			if (args.confirm)
			{
				var msg = "<h1>" + _("Attention!") + "</h1><br/>";
				msg = msg + "<p>" +
					_("Installing a system update is a significant change to this system and could have impact to other systems. ") +
					_("In normal case, trouble-free use by users is not possible during the update, since system services may need to be restarted. ") +
					_("Thus, updates shouldn't be installed on a live system. ") +
					_("It is also recommended to evaluate the update in a test environment and to create a backup of the system.") +
					"</p>";
				msg = msg + "<p>" +
					_("During setup, the web server may be stopped, leading to a termination of the HTTP connection. ") +
					_("Nonetheless, the update proceeds and the update can be monitored from a new UMC session. ") +
					_("Logfiles can be found in the directory /var/log/univention/.") +
					"</p>";
				msg = msg + "<p>" +
					_("Please also consider the release notes, changelogs and references posted in the <a href='http://forum.univention.de'>Univention Forum</a>.") +
					"</p>";
				msg = msg + "<p><strong>" +
					_("DO NOT power off the system during the update.") +
					"</strong> " +
					_("The update can take a long time and the system may respond slowly. You may be temporarily unable to log in.") +
					" <strong>" +
					_("Again, DO NOT power off the system even in these cases!") +
					"</strong></p>";
				if (typeof(args.confirm) == 'string')
				{
					msg = msg + "<p>" + args.confirm + "</p>";
				}
				else
				{
					msg = msg + "<p>" +
						_("Do you really wish to proceed?") +
						"</p>";
				}

				dialog.confirm(msg,
				[
					{
						label:		_('Cancel')
					},
					{
						label:		_('Install'),
						'default':	true,
						callback:	lang.hitch(this, function() {
							args.confirm = false;
							this._call_installer(args);
						})
					}
				]);

				return;
			}

			this.standby(true);

			this.umcpCommand('updater/installer/execute', {
				job:	args.job,
				detail:		args.detail ? args.detail : ''
			}).then(lang.hitch(this, function(data) {
				this.standby(false);
				if (data.result.status === 0)
				{
					this._switch_to_progress_page();
				}
				else
				{
					dialog.alert(lang.replace(_("The Univention Updater action could not be started [Error {status}]: {message}"), data.result));
				}
			}),
			// Strongly needed: an error callback! In this case, the built-in error processing
			// (popup or login prompt) is well suited for the situation, so we don't disable it.
			lang.hitch(this, function() {
				this.standby(false);
			}));
		},


		// Switches to the progress view: all tabs but the 'update in progess' will disappear.
		// Remembers the currently selected tab and will restore it when finished.
		// NOTE that we don't pass any args to the progress page since it is able
		//		to fetch them all from the AT job.
		_switch_to_progress_page: function() {

			try
			{
				this.selectChild(this._progress);

				this._progress.startWatching();
			}
			catch(error)
			{
				console.error("switch_progress: " + error.message);
			}
		},

		// We must establish a NO ERROR callback too, so we can reset
		// the error status
		handleQuerySuccess: function(subject) {

			//console.error("QUERY '" + subject + "' -> SUCCESS");
			if (this._connection_status !== 0)
			{
				this._reset_error_status();
			}
		},

		// Recover after any kind of long-term failure:
		//
		//	-	set error counter to zero
		//	-	set connection status to ok
		//	-	close eventually opened 'connection lost' dialog
		//	-	refresh Updates page
		//	-	restart polling
		_reset_error_status: function() {

			this._connection_status = 0;
			this._error_count = 0;
			if (this._busy_dialog)
			{
				this._busy_dialog.hide();
				this._busy_dialog.destroy();
				this._busy_dialog = null;
			}
		},

		// Handles gracefully all things related to fatal query errors while
		// an installer call is running. The background is that all polling
		// queries are done with 'handleErrors=false', and their corresponding
		// Error callback hands everything over to this function. So it could
		// theoretically even survive a reboot...
		handleQueryError: function(subject, data) {

			try
			{
				// While the login dialog is open -> all queries return at the
				// error callback, but without data! (should be documented)
				if (typeof(data) == 'undefined')
				{
					//console.error("QUERY '" + subject + "' without DATA");
					return;
				}
				//console.error("QUERY '" + subject + "' STATUS = " + data.status);
				if (data.status == 401)
				{
					if (this._connection_status != 2)
					{
						this._connection_status = 2;

						if (this._busy_dialog)
						{
							this._busy_dialog.hide();
							this._busy_dialog.destroy();
							this._busy_dialog = null;
						}

						dialog.login().then(lang.hitch(this, function() {
							// if authenticated again -> reschedule refresh queries, Note that these
							// methods are intelligent enough to do nothing if the timer in question
							// is already active.
							this._updates.refreshPage();
							this._updates.startPolling();
							this._progress.startPolling();
						})
						);


						dialog.notify(_("Your current session has expired, or the connection to the server was lost. You must authenticate yourself again."));
					}
	//				else
	//				{
	//					console.error("QUERY '" + subject + "' -> AGAIN STATUS 401");
	//				}
				}
				else
				{
					this._connection_status = 1;

					this._error_count = this._error_count + 1;
					if (this._error_count < 5)
					{
						// this toaster thingy is not really usable!
						//dialog.notify(_("Connection to server lost. Trying to reconnect."));
					}
					else
					{
						if (this._busy_dialog === null)
						{
							this._busy_dialog = new Dialog({
								title:		_("Connection lost!"),
								closable:	false,
								style:		"width: 300px",
								'class':	'umcConfirmDialog'
							});
							this._busy_dialog.attr("content",
									'<p>' + _("The connection to the server was lost, trying to reconnect. You may need to re-authenticate when the connection is restored.") + '</p>' +
									'<p>' + _("Alternatively, you may close the current Management Console window, wait some time, and try to open it again.") + '</p>');
							this._busy_dialog.show();
						}
					}
				}
			}
			catch(error)
			{
				console.error("HANDLE_ERRORS: " + error.message);
			}
		}
	});

});
