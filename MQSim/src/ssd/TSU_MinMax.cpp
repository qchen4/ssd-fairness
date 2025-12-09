#include <limits>
#include "TSU_MinMax.h"

namespace SSD_Components
{
	TSU_MinMax::TSU_MinMax(const sim_object_id_type& id, FTL* ftl, NVM_PHY_ONFI_NVDDR2* NVMController,
		unsigned int ChannelCount, unsigned int chip_no_per_channel, unsigned int DieNoPerChip, unsigned int PlaneNoPerDie,
		sim_time_type WriteReasonableSuspensionTimeForRead, sim_time_type EraseReasonableSuspensionTimeForRead,
		sim_time_type EraseReasonableSuspensionTimeForWrite,
		bool EraseSuspensionEnabled, bool ProgramSuspensionEnabled)
		: TSU_Base(id, ftl, NVMController, Flash_Scheduling_Type::MINMAX, ChannelCount, chip_no_per_channel, DieNoPerChip, PlaneNoPerDie,
			EraseSuspensionEnabled, ProgramSuspensionEnabled, WriteReasonableSuspensionTimeForRead, EraseReasonableSuspensionTimeForRead,
			EraseReasonableSuspensionTimeForWrite),
		UserReadTRQueue(nullptr), UserWriteTRQueue(nullptr), GCReadTRQueue(nullptr), GCWriteTRQueue(nullptr),
		GCEraseTRQueue(nullptr), MappingReadTRQueue(nullptr), MappingWriteTRQueue(nullptr)
	{
		flow_state.resize(MAX_SUPPORT_STREAMS);

		UserReadTRQueue = new Flash_Transaction_Queue * [channel_count];
		UserWriteTRQueue = new Flash_Transaction_Queue * [channel_count];
		GCReadTRQueue = new Flash_Transaction_Queue * [channel_count];
		GCWriteTRQueue = new Flash_Transaction_Queue * [channel_count];
		GCEraseTRQueue = new Flash_Transaction_Queue * [channel_count];
		MappingReadTRQueue = new Flash_Transaction_Queue * [channel_count];
		MappingWriteTRQueue = new Flash_Transaction_Queue * [channel_count];

		for (unsigned int channelID = 0; channelID < channel_count; channelID++)
		{
			UserReadTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
			UserWriteTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
			GCReadTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
			GCWriteTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
			GCEraseTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
			MappingReadTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
			MappingWriteTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];

			for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
			{
				UserReadTRQueue[channelID][chip_cntr].Set_id("MM_User_Read_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
				UserWriteTRQueue[channelID][chip_cntr].Set_id("MM_User_Write_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
				GCReadTRQueue[channelID][chip_cntr].Set_id("MM_GC_Read_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
				GCWriteTRQueue[channelID][chip_cntr].Set_id("MM_GC_Write_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
				GCEraseTRQueue[channelID][chip_cntr].Set_id("MM_GC_Erase_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
				MappingReadTRQueue[channelID][chip_cntr].Set_id("MM_Mapping_Read_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
				MappingWriteTRQueue[channelID][chip_cntr].Set_id("MM_Mapping_Write_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			}
		}
	}

	TSU_MinMax::~TSU_MinMax()
	{
		for (unsigned int channelID = 0; channelID < channel_count; channelID++)
		{
			delete[] UserReadTRQueue[channelID];
			delete[] UserWriteTRQueue[channelID];
			delete[] GCReadTRQueue[channelID];
			delete[] GCWriteTRQueue[channelID];
			delete[] GCEraseTRQueue[channelID];
			delete[] MappingReadTRQueue[channelID];
			delete[] MappingWriteTRQueue[channelID];
		}
		delete[] UserReadTRQueue;
		delete[] UserWriteTRQueue;
		delete[] GCReadTRQueue;
		delete[] GCWriteTRQueue;
		delete[] GCEraseTRQueue;
		delete[] MappingReadTRQueue;
		delete[] MappingWriteTRQueue;
	}

	void TSU_MinMax::Start_simulation() {}
	void TSU_MinMax::Validate_simulation_config() {}
	void TSU_MinMax::Execute_simulator_event(MQSimEngine::Sim_Event* event) {}

	void TSU_MinMax::Schedule()
	{
		opened_scheduling_reqs--;
		if (opened_scheduling_reqs > 0)
			return;
		if (opened_scheduling_reqs < 0)
			PRINT_ERROR("TSU_MinMax: Illegal status!");
		if (transaction_receive_slots.size() == 0)
			return;

		for (auto it = transaction_receive_slots.begin(); it != transaction_receive_slots.end(); it++)
		{
			switch ((*it)->Type)
			{
			case Transaction_Type::READ:
				switch ((*it)->Source)
				{
				case Transaction_Source_Type::CACHE:
				case Transaction_Source_Type::USERIO:
					UserReadTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
					break;
				case Transaction_Source_Type::MAPPING:
					MappingReadTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
					break;
				case Transaction_Source_Type::GC_WL:
					GCReadTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
					break;
				default:
					PRINT_ERROR("TSU_MinMax: Unknown source type for read transaction")
				}
				break;
			case Transaction_Type::WRITE:
				switch ((*it)->Source)
				{
				case Transaction_Source_Type::CACHE:
				case Transaction_Source_Type::USERIO:
					UserWriteTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
					break;
				case Transaction_Source_Type::MAPPING:
					MappingWriteTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
					break;
				case Transaction_Source_Type::GC_WL:
					GCWriteTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
					break;
				default:
					PRINT_ERROR("TSU_MinMax: Unknown source type for write transaction")
				}
				break;
			case Transaction_Type::ERASE:
				GCEraseTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
				break;
			default:
				break;
			}
		}
		transaction_receive_slots.clear();

		for (flash_channel_ID_type channelID = 0; channelID < channel_count; channelID++)
		{
			if (_NVMController->Get_channel_status(channelID) == BusChannelStatus::IDLE)
			{
				for (unsigned int i = 0; i < chip_no_per_channel; i++)
				{
					NVM::FlashMemory::Flash_Chip* chip = _NVMController->Get_chip(channelID, Round_robin_turn_of_channel[channelID]);
					if (!service_read_transaction(chip))
						if (!service_write_transaction(chip))
							service_erase_transaction(chip);
					Round_robin_turn_of_channel[channelID] = (flash_chip_ID_type)(Round_robin_turn_of_channel[channelID] + 1) % chip_no_per_channel;
					if (_NVMController->Get_channel_status(chip->ChannelID) != BusChannelStatus::IDLE)
						break;
				}
			}
		}
	}

	void TSU_MinMax::Report_results_in_XML(std::string name_prefix, Utils::XmlWriter& xmlwriter)
	{
		name_prefix = name_prefix + ".TSU_MinMax";
		xmlwriter.Write_open_tag(name_prefix);
		TSU_Base::Report_results_in_XML(name_prefix, xmlwriter);
		xmlwriter.Write_close_tag();
	}

	TSU_MinMax::FlowState& TSU_MinMax::get_flow_state(stream_id_type sid)
	{
		if (sid >= flow_state.size())
			flow_state.resize(static_cast<size_t>(sid) + 1);
		return flow_state[sid];
	}

	NVM_Transaction_Flash* TSU_MinMax::pick_minmax_user_transaction(Flash_Transaction_Queue& queue)
	{
		if (queue.size() == 0)
			return nullptr;

		auto best_it = queue.begin();
		double best_metric = std::numeric_limits<double>::max();

		for (auto it = queue.begin(); it != queue.end(); ++it)
		{
			FlowState& fs = get_flow_state((*it)->Stream_id);
			double candidate = (fs.service + 1.0) / fs.weight;
			if (candidate < best_metric)
			{
				best_metric = candidate;
				best_it = it;
			}
		}

		NVM_Transaction_Flash* chosen = *best_it;
		FlowState& fs = get_flow_state(chosen->Stream_id);
		fs.service += 1.0;

		if (best_it != queue.begin())
		{
			queue.remove(best_it);
			queue.push_front(chosen);
		}
		return chosen;
	}

	bool TSU_MinMax::service_read_transaction(NVM::FlashMemory::Flash_Chip* chip)
	{
		Flash_Transaction_Queue *sourceQueue1 = NULL, *sourceQueue2 = NULL;

		//Flash transactions that are related to FTL mapping data have the highest priority
		if (MappingReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue1 = &MappingReadTRQueue[chip->ChannelID][chip->ChipID];
			if (ftl->GC_and_WL_Unit->GC_is_in_urgent_mode(chip) && GCReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
				sourceQueue2 = &GCReadTRQueue[chip->ChannelID][chip->ChipID];
			else if (UserReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
				sourceQueue2 = &UserReadTRQueue[chip->ChannelID][chip->ChipID];
		}
		else if (ftl->GC_and_WL_Unit->GC_is_in_urgent_mode(chip))
		{
			if (GCReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
			{
				sourceQueue1 = &GCReadTRQueue[chip->ChannelID][chip->ChipID];
				if (UserReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
					sourceQueue2 = &UserReadTRQueue[chip->ChannelID][chip->ChipID];
			}
			else if (GCWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0 || GCEraseTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
			{
				return false;
			}
			else if (UserReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
			{
				sourceQueue1 = &UserReadTRQueue[chip->ChannelID][chip->ChipID];
			}
			else
				return false;
		}
		else
		{
			if (UserReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
			{
				sourceQueue1 = &UserReadTRQueue[chip->ChannelID][chip->ChipID];
				if (GCReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
					sourceQueue2 = &GCReadTRQueue[chip->ChannelID][chip->ChipID];
			}
			else if (UserWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
				return false;
			else if (GCReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
				sourceQueue1 = &GCReadTRQueue[chip->ChannelID][chip->ChipID];
			else
				return false;
		}

		bool suspensionRequired = false;
		ChipStatus cs = _NVMController->GetChipStatus(chip);
		switch (cs)
		{
		case ChipStatus::IDLE:
			break;
		case ChipStatus::WRITING:
			if (!programSuspensionEnabled || _NVMController->HasSuspendedCommand(chip))
				return false;
			if (_NVMController->Expected_finish_time(chip) - Simulator->Time() < writeReasonableSuspensionTimeForRead)
				return false;
			suspensionRequired = true;
		case ChipStatus::ERASING:
			if (!eraseSuspensionEnabled || _NVMController->HasSuspendedCommand(chip))
				return false;
			if (_NVMController->Expected_finish_time(chip) - Simulator->Time() < eraseReasonableSuspensionTimeForRead)
				return false;
			suspensionRequired = true;
		default:
			return false;
		}

		if (sourceQueue1 == &UserReadTRQueue[chip->ChannelID][chip->ChipID])
			pick_minmax_user_transaction(*sourceQueue1);
		if (sourceQueue2 == &UserReadTRQueue[chip->ChannelID][chip->ChipID])
			pick_minmax_user_transaction(*sourceQueue2);

		return issue_command_to_chip(sourceQueue1, sourceQueue2, Transaction_Type::READ, suspensionRequired);
	}

	bool TSU_MinMax::service_write_transaction(NVM::FlashMemory::Flash_Chip* chip)
	{
		Flash_Transaction_Queue *sourceQueue1 = NULL, *sourceQueue2 = NULL;

		if (ftl->GC_and_WL_Unit->GC_is_in_urgent_mode(chip))
		{
			if (GCWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
			{
				sourceQueue1 = &GCWriteTRQueue[chip->ChannelID][chip->ChipID];
				if (UserWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
					sourceQueue2 = &UserWriteTRQueue[chip->ChannelID][chip->ChipID];
			}
			else if (GCEraseTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
				return false;
			else if (UserWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
				sourceQueue1 = &UserWriteTRQueue[chip->ChannelID][chip->ChipID];
			else
				return false;
		}
		else
		{
			if (UserWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
			{
				sourceQueue1 = &UserWriteTRQueue[chip->ChannelID][chip->ChipID];
				if (GCWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
					sourceQueue2 = &GCWriteTRQueue[chip->ChannelID][chip->ChipID];
			}
			else if (GCWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
				sourceQueue1 = &GCWriteTRQueue[chip->ChannelID][chip->ChipID];
			else
				return false;
		}

		bool suspensionRequired = false;
		ChipStatus cs = _NVMController->GetChipStatus(chip);
		switch (cs)
		{
		case ChipStatus::IDLE:
			break;
		case ChipStatus::ERASING:
			if (!eraseSuspensionEnabled || _NVMController->HasSuspendedCommand(chip))
				return false;
			if (_NVMController->Expected_finish_time(chip) - Simulator->Time() < eraseReasonableSuspensionTimeForWrite)
				return false;
			suspensionRequired = true;
		default:
			return false;
		}

		if (sourceQueue1 == &UserWriteTRQueue[chip->ChannelID][chip->ChipID])
			pick_minmax_user_transaction(*sourceQueue1);
		if (sourceQueue2 == &UserWriteTRQueue[chip->ChannelID][chip->ChipID])
			pick_minmax_user_transaction(*sourceQueue2);

		return issue_command_to_chip(sourceQueue1, sourceQueue2, Transaction_Type::WRITE, suspensionRequired);
	}

	bool TSU_MinMax::service_erase_transaction(NVM::FlashMemory::Flash_Chip* chip)
	{
		if (GCEraseTRQueue[chip->ChannelID][chip->ChipID].size() == 0)
			return false;
		if (_NVMController->GetChipStatus(chip) != ChipStatus::IDLE)
			return false;
		return issue_command_to_chip(&GCEraseTRQueue[chip->ChannelID][chip->ChipID], NULL, Transaction_Type::ERASE, false);
	}
}

