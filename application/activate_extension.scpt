--for debugging please use log lines. The script should be updated for each of major macOS upgrade. ToDo(vk):Next update for macOS:15.x
--for testing comment out line: 'tell application "Casablanca Application"', and respective line: 'end tell'

on run argv
	set is_first_start to item 1 of argv
	--display dialog is_first_start
	--set is_first_start to "true"
	set out to main(is_first_start)
end run

on exit_casablanca()
	tell application "Casablanca Application"
		quit
	end tell
	return "Exit"
end exit_casablanca

on display_alert_with_img(msg, title_, img_name)
	try
	tell application "Casablanca Application"
		set userChoice to showDialog message msg title title_ image img_name
		if userChoice is "OK" then
			return "OK"
		else if userChoice is "Cancelled" then
			return "Cancelled"
		end if
	end tell
	on error errMsg
		log "Error occurred "&errMsg
		return errMsg
	end try
end display_alert_with_img

on opensystemextensionMacOS15()
	tell application "System Settings" to quit
	delay 1.0

	set permission_msg to "Allow Casablanca Camera Extension in the next screen by clicking on the toggle button"
	set permission_title to "Casablanca Camera Extension needs Authentication"
	set permission_img to "CasablancaAllowVirtualCameraMacOS15"

	set is_alert_ok to display_alert_with_img(permission_msg, permission_title, permission_img)

	if is_alert_ok contains "Cancel" then
		exit_casablanca()
	end if

	set cmd to "open x-apple.systempreferences:com.apple.LoginItems-Settings.extension"
	set cmdResult to do shell script cmd
	log cmdResult
	delay 1.0


	tell application "System Events"
		tell process "System Settings"
			delay 1.0
			-- Click the "Camera Extensions" static text
			click button 2 of group 3 of scroll area 1 of group 1 of group 2 of splitter group 1 of group 1 of window "Login Items & Extensions"
			delay 1.0
		end tell
	end tell


end opensystemextensionMacOS15

on display_dialog(message, title)
	tell application "Casablanca Application"
		set userChoice to display dialog message buttons {"OK"} default button "OK" with title title with icon note
	end tell
	return userChoice
end display_dialog

on display_dialog_with_timeout(message, title, give_up_after_time)
	tell application "Casablanca Application"
		display dialog message buttons {"OK"} default button "OK" with icon note with title title giving up after give_up_after_time
	end tell
end display_dialog_with_timeout

on notification_with_sound(msg, title_, sound_)
	tell application "Casablanca Application"
		notify message msg title title_ sound sound_
	end tell
end notification_with_sound

on open_casablanca_allow_window(osVersion)
	tell application "System Settings" to quit
	delay 1.0
	if osVersion starts with "15." then
		set cmd to "open x-apple.systempreferences:com.apple.GeneralSettings"
	else
		set cmd to "open x-apple.systempreferences:com.apple.preference.security?Security"
	end if
	set cmdResult to do shell script cmd
	log cmdResult
	return cmdResult
end open_casablanca_allow_window

on open_allow_window_for_casablanca_extension_osx_13_on_error(display_dialog)

	try

		if display_dialog then
			tell application "Casablanca Application"
			set permission_msg to "We are unable to automate, please click on allow in the next screen"
			set permission_title to "Casablanca Camera Extension needs Authentication"
			set permission_img to "CasablancaAllowVirtualCamera"

			set is_alert_ok to display_alert_with_img(permission_msg, permission_title, permission_img)
				if is_alert_ok contains "Cancel" then
					exit_casablanca()
				end if
			end tell
		end if

		open_casablanca_allow_window()
		wait_for_acquiring_manual_permissions()

	on error errMsg
		log "Error Occured: " & errMsg
		open_casablanca_allow_window()
		return errMsg

	end try
	return
end open_allow_window_for_casablanca_extension_osx_13_on_error



on play_tutorial(osVersion)
	tell application "QuickTime Player"
		if osVersion starts with "15." then
			open POSIX file "/Library/Application Support/Casablanca/app-ort/assets/CasablancaAfterInstallAllowTutorialMacOS15.mp4"
		else
			open POSIX file "/Library/Application Support/Casablanca/app-ort/assets/CasablancaAfterInstallAllowTutorial.mp4"
		end if

		set theMovie to the front document
		set current time of theMovie to 0 -- Ensure playback starts from the beginning
		set rate of theMovie to 0.5 -- Set playback speed to 0.5x
		play theMovie

		-- Loop to check if the movie is still playing
		repeat while playing of theMovie is true
			delay 2 -- Checks every 2 seconds
		end repeat

		close theMovie saving no -- Close the movie without saving
		quit -- Quit QuickTime Player
	end tell
	delay 1
end play_tutorial


on set_restart_flag()
	set theFilePath to "/Library/Application Support/Casablanca/isRestart.txt"
	set theText to "true"

	try

		set fileRef to open for access POSIX file theFilePath with write permission

		set eof of fileRef to 0
		write theText to fileRef

		close access fileRef
	on error errMsg
		display dialog "Error writing to file: " & errMsg
		try
			close access fileRef
		end try
	end try
end set_restart_flag

on click_on_allow(osVersion)

	if osVersion starts with "13." then
		set group_id to 4
	else if osVersion starts with "14." then
		set group_id to 5
	else if osVersion starts with "15." then
		opensystemextensionMacOS15()
		return
	end if

	tell application "System Settings" to quit
	delay 1.0
	--tell application "Casablanca Application"
	tell application "System Settings"
		activate
		reveal pane id "com.apple.settings.PrivacySecurity.extension"
		delay 1.0
	end tell
	tell application "System Events"
		tell window 1 of application process "System Settings"
			tell button 1 of group group_id of scroll area 1 of group 1 of group 2 of splitter group 1 of group 1
				click
			end tell
		end tell
	end tell
	--end tell
end click_on_allow

on is_allowed_to_automate()
	try
		set is_permission_to_automate to do shell script "/Library/Application\\ Support/Casablanca/app-ort/application/CheckAccessibility"
		--set is_permission_to_automate to do shell script "/Users/vinayak/PycharmProjects/app-ort/CheckAccessibility"
		log is_permission_to_automate
		return is_permission_to_automate
	on error errMsg
		display dialog "Error: " & e & " Error Number: " & n
	end try
end is_allowed_to_automate

on open_accessibiliy_window()
	tell application "System Settings" to quit
	delay 1.0
	set cmd to "open x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
	set cmdResult to do shell script cmd
	log cmdResult
	return cmdResult
end open_accessibiliy_window


on wait_for_acquiring_manual_permissions()
	set counter to 0
	-- ToDo(vk) change the timer to 60 seconds
	repeat while counter is less than 60
		set is_permission_given_to_extension to run_systemextension_cmd()
		if is_permission_given_to_extension contains "activated enabled" then
			display_dialog("Permission Acquired by Camera Extension, Restarting Casalanca Application Now!")
			set_restart_flag()
			exit repeat
		end if
		delay 1.0
		set counter to counter + 1
	end repeat
	-- timer is over, display
	display_dialog_with_timeout("Could not acquire permission, timed out", "Exiting Casablanca...", 10)
	exit_casablanca()

end wait_for_acquiring_manual_permissions


on display_options(osVersion, is_first_start)
	--Automate automatically if the automation permission is given
	set is_permission_to_automate to is_allowed_to_automate()
	log is_permission_to_automate
	if is_permission_to_automate = "true" then
		notification_with_sound("Please Authenticate now for acquiring Permissions for Casablanca Camera Extension...", "Requesting Authentication", "Submarine")
		click_on_allow(osVersion)
		return
	end if

	tell application "Casablanca Application"
		set userChoice to display dialog "Casablanca needs permissions for Camera Extension, we can automate that task for you or you could manually allow from Privacy and Security" with title "Casablanca needs Authentication" buttons {"Cancel", "Watch Tutorial", "Automate"} default button "Automate" with icon note
	end tell


	if button returned of userChoice is "Watch Tutorial" then
		play_tutorial(osVersion)
		tell application "Casablanca Application"
			set is_open_settings to display dialog "Now that you know what to do, Please allow Casablanca App from Systems Settings" with title "Allow Casablanca" buttons {"Cancel", "Open Settings"} default button "Open Settings" with icon note
		end tell
		if button returned of is_open_settings is "Open Settings" then
			open_casablanca_allow_window(osVersion)
			wait_for_acquiring_manual_permissions()

		end if

		return "Tutorial Played and allow window opened"

	else if button returned of userChoice is "Automate" then
		set accessibility_msg to "Please click on the toggle button to allow Casablanca Application in the next window"
		set accessibility_title to "Casablanca needs Permissions to automate"
		set accessibility_img to "CasablancaAllowAccessibility"

		log "Automating"
		if is_first_start = true then
			display_dialog("To Automate we need permissions in Accessebility.\n\nPlease click on allow in Accessibiity app will restart automatically once the permission is given", "Please click on Allow")
			click_on_allow(osVersion)
			set_restart_flag()
		else
			set is_permission_to_automate to is_allowed_to_automate()
			log is_permission_to_automate
			if is_permission_to_automate = "true" then
				click_on_allow(osVersion)
				return
			else
				set is_alert_ok to display_alert_with_img(accessibility_msg, accessibility_title, accessibility_img)
				if is_alert_ok contains "Cancel" then
					exit_casablanca()
				end if
				open_accessibiliy_window()
				set counter to 0
				repeat while counter is less than 60
					set is_permission_to_automate to is_allowed_to_automate()
					set counter to counter + 1
					delay 1.0
					if is_permission_to_automate = "true" then
						notification_with_sound("Restarting Casablanca Application...", "Permissions given", "Submarine")
						set_restart_flag()
						log "Clicked on allow"
						return
						exit repeat
					end if
				end repeat
				--permission for automation not given exiting
				notification_with_sound("Permission to Automate not given, Exiting Casablanca Application...", "Exiting...", "Submarine")
				exit_casablanca()
			end if
		end if


		log "Permission for Automatation initiated"
		return "Permission for Automatation initiated"
	else
		open_casablanca_allow_window()
		wait_for_acquiring_manual_permissions()

	end if


end display_options


on click_allow_on_casablanca_extension(osVersion, is_first_start)
	try

		display_options(osVersion, is_first_start)
	on error errMsg
		if errMsg contains "AppleEvent handler failed" then
			set display_dialog to true
			open_allow_window_for_casablanca_extension_osx_13_on_error(display_dialog)
		else if errMsg contains "User cancelled" then
			notification_with_sound("User cancelled...", "Exiting Casablanca Application", "Submarine")
			exit_casablanca()
		else
			log "Error Occurred " & errMsg
			if errMsg contains "is not allowed assistive access" then
				-- If clicked on automatation and if permissions are not given, then this exception will be raised. This means that user tried to automate, check for 30 seconds if they click on Allow under Accessibility
				--display dialog "is not allowed assistive access, in the exception part, ideally we should not have any exceptions here, come back to this code and check what is happening"
				set counter to 0
				repeat while counter is less than 30
					set is_permission_to_automate to is_allowed_to_automate()
					set counter to counter + 1
					delay 1.0
					if is_permission_to_automate = "true" then

						log "Restarting Casablanca"
						notification_with_sound("Permission was given by user.\n\nRestarting Casablanca......", "Casablanca Application", "Submarine")
						set_restart_flag()

						exit repeat
					end if

				end repeat

			end if
			return errMsg
		end if
		delay 10
	end try

end click_allow_on_casablanca_extension



on execute_activation_cmd()
	set cmd_activate to "'/Applications/Casablanca Application.app/Contents/MacOS/Casablanca Application' Function=\"Activate\""
	set cmd_activateResult to do shell script cmd_activate
end execute_activation_cmd


on run_systemextension_cmd()
	try
		set cmd to "systemextensionsctl list | grep 'com\\.casablanca'"
		set cmdResult to do shell script cmd
		return cmdResult
	on error errorMessage
		-- Usually error occurs when systemextensionsctl list command returns nothing, which indicates that activation command should run
		log "Error Occurred: " & errorMessage
		log "Trying to activate Casablanca Camera"
		execute_activation_cmd()
		return
	end try
end run_systemextension_cmd


on main(is_first_start)

	set osVersion to do shell script "sw_vers -productVersion"
	tell application "System Settings" to quit
	delay 1.0

	set cmdResult to run_systemextension_cmd()
	if cmdResult contains "activated enabled" then
		log "Camera Extension already activated"
		return "Camera Extension already activated"

	else if cmdResult contains "activated waiting for user" or cmdResult contains "activated disabled" then
		try
			log "Trying to Open Security and Privacy to get the permission for Casablanca's Camera Extensions"

			click_allow_on_casablanca_extension(osVersion, is_first_start)
		end try
	else
		-- when the command does not return anything, which suggests this commands needs to be run
		log "Trying to activate Casablanca Camera"
		display notification "Activating Casablanca's Extension" sound name "Submarine" with title "Activating Casablanca"
		execute_activation_cmd()

	end if
end main

