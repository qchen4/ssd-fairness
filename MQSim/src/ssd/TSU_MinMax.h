#ifndef TSU_MINMAX_H
#define TSU_MINMAX_H

#include <vector>
#include "TSU_Base.h"
#include "Flash_Transaction_Queue.h"
#include "SSD_Defs.h"

namespace SSD_Components
{
	class TSU_MinMax : public TSU_Base
	{
	public:
		TSU_MinMax(const sim_object_id_type& id, FTL* ftl, NVM_PHY_ONFI_NVDDR2* NVMController,
			unsigned int ChannelCount, unsigned int chip_no_per_channel, unsigned int DieNoPerChip, unsigned int PlaneNoPerDie,
			sim_time_type WriteReasonableSuspensionTimeForRead, sim_time_type EraseReasonableSuspensionTimeForRead,
			sim_time_type EraseReasonableSuspensionTimeForWrite,
			bool EraseSuspensionEnabled, bool ProgramSuspensionEnabled);
		~TSU_MinMax();

		void Schedule() override;
		void Start_simulation() override;
		void Validate_simulation_config() override;
		void Execute_simulator_event(MQSimEngine::Sim_Event* event) override;
		void Report_results_in_XML(std::string name_prefix, Utils::XmlWriter& xmlwriter) override;

	private:
		Flash_Transaction_Queue** UserReadTRQueue;
		Flash_Transaction_Queue** UserWriteTRQueue;
		Flash_Transaction_Queue** GCReadTRQueue;
		Flash_Transaction_Queue** GCWriteTRQueue;
		Flash_Transaction_Queue** GCEraseTRQueue;
		Flash_Transaction_Queue** MappingReadTRQueue;
		Flash_Transaction_Queue** MappingWriteTRQueue;

		struct FlowState
		{
			double weight;
			double service;
			FlowState() : weight(1.0), service(0.0) {} //TODO: wire weight to config if priorities are added
		};

		std::vector<FlowState> flow_state;

		FlowState& get_flow_state(stream_id_type sid);
		NVM_Transaction_Flash* pick_minmax_user_transaction(Flash_Transaction_Queue& queue);

		bool service_read_transaction(NVM::FlashMemory::Flash_Chip* chip) override;
		bool service_write_transaction(NVM::FlashMemory::Flash_Chip* chip) override;
		bool service_erase_transaction(NVM::FlashMemory::Flash_Chip* chip) override;
	};
}

#endif //!TSU_MINMAX_H

